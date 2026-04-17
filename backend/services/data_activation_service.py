"""
Data Activation Service — Astra 360
4-Stage fallback-driven ingestion pipeline:
  Stage 1 → Structured table extraction (CSV/Excel/PDF tables via pandas)
  Stage 2 → Regex heuristic extraction (from raw text, multi-bank patterns)
  Stage 3 → LLM categorization (only if transactions already found)
  Stage 4 → LLM fallback extraction (only if stages 1+2 both yield 0 results)
"""

import os
import re
import json
import logging
import datetime
import hashlib
import pandas as pd
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session

from database import SessionLocal
from models import (
    User, Transaction, Bill, Loan, UserFinancialSummary,
    UserProcessingStatus, get_user_by_external_id
)
from rag.document_processor import parse_document
from rag.embeddings import generate_embeddings, generate_embeddings_async
from rag.vector_store import insert_transactions, insert_insight
from agents.wealth_agent import call_llm, LLM_MODEL

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
MIN_VALID_FIELDS = 3          # Accept partial records with at least 3 of 4 fields
MAX_TEXT_FOR_LLM  = 4000      # Performance guard — truncate before sending to LLM
LOW_CONFIDENCE_THRESHOLD = 0.3


# ─────────────────────────────────────────────
# KEYWORD CATEGORY RULES (pre-LLM, fast)
# ─────────────────────────────────────────────
CATEGORY_RULES: List[Tuple[List[str], str]] = [
    (["swiggy", "zomato", "dominos", "pizza", "kfc", "mcdonald", "blinkit", "dunzo"], "Food & Dining"),
    (["amazon", "flipkart", "myntra", "meesho", "ajio", "nykaa", "snapdeal"], "Shopping"),
    (["uber", "ola", "rapido", "irctc", "railway", "makemytrip", "goibibo", "indigo", "spicejet"], "Travel"),
    (["netflix", "spotify", "prime", "hotstar", "disney", "youtube", "zee5", "subscription"], "Subscriptions"),
    (["salary", "payroll", "employer", "credited by", "neft cr"], "Salary"),
    (["emi", "loan", "home loan", "car loan", "bajaj", "hdfc loan", "icici loan"], "EMI / Loans"),
    (["electricity", "water", "gas", "broadband", "airtel", "jio", "bsnl", "recharge", "utility"], "Utilities"),
    (["rent", "landlord", "house rent", "pg", "accommodation"], "Rent / Housing"),
    (["hospital", "pharmacy", "medicine", "apollo", "medplus", "health"], "Healthcare"),
    (["atm", "cash withdrawal", "cash deposit"], "Cash"),
    (["interest", "fd interest", "dividend", "mutual fund", "sip", "zerodha", "groww"], "Investments"),
    (["tax", "tds", "gst", "income tax"], "Tax"),
    (["insurance", "lic", "premium"], "Insurance"),
    (["transfer", "upi", "neft", "imps", "rtgs", "self transfer"], "Transfers"),
]

def _keyword_category(description: str) -> Optional[str]:
    """Fast keyword-based categorization before LLM."""
    desc_lower = description.lower()
    for keywords, category in CATEGORY_RULES:
        if any(kw in desc_lower for kw in keywords):
            return category
    return None


# ─────────────────────────────────────────────
# DEDUPLICATION
# ─────────────────────────────────────────────
def _normalize(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", str(text)).lower()

def _tx_hash(date: str, amount: float, description: str, index: int, user_id: int) -> str:
    raw = f"{user_id}-{date}-{round(amount, 2)}-{_normalize(description)}-{index}"
    return hashlib.md5(raw.encode()).hexdigest()


# ─────────────────────────────────────────────
# DATE PARSING — multi-format
# ─────────────────────────────────────────────
DATE_FORMATS = [
    "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y",
    "%d/%m/%y",  # DD/MM/YY — SBI, Axis short format
    "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y",
    "%d-%b-%Y", "%d/%b/%Y", "%d %b %y", "%d-%b-%y",
    "%Y%m%d",
]

def _parse_date(raw: str) -> Optional[datetime.datetime]:
    raw = str(raw).strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.datetime.strptime(raw, fmt)
        except ValueError:
            pass
    return None

DATE_RE = re.compile(
    r"\b(\d{4}[-/]\d{2}[-/]\d{2}"          # YYYY-MM-DD / YYYY/MM/DD
    r"|\d{2}[-/]\d{2}[-/]\d{4}"            # DD-MM-YYYY / DD/MM/YYYY
    r"|\d{2}[-/ ]\w{3}[-/ ]\d{2,4}"        # DD-Mon-YY(YY)
    r"|\d{1,2} \w+ \d{4})\b",              # D Month YYYY
    re.IGNORECASE
)

AMOUNT_RE = re.compile(
    r"(?:₹|Rs\.?|INR)?\s*([0-9]{1,3}(?:,[0-9]{3})*(?:\.[0-9]{1,2})?)"
)


# ─────────────────────────────────────────────
# STAGE 1 — STRUCTURED TABLE EXTRACTION
# ─────────────────────────────────────────────
COLUMN_ALIASES = {
    "date":        ["date", "txn date", "transaction date", "value date", "posting date", "trans date"],
    "amount":      ["amount", "amt", "transaction amount", "net amount"],
    "debit":       ["debit", "dr", "debit amount", "withdrawal", "withdrawal amt", "withdrawals"],
    "credit":      ["credit", "cr", "credit amount", "deposit", "deposit amt", "deposits"],
    "type":        ["type", "tx type", "transaction type", "dr/cr"],
    "description": ["description", "narration", "particulars", "details", "remarks", "transaction details", "transaction remark"],
}

def _find_column(df: pd.DataFrame, aliases: List[str]) -> Optional[str]:
    """Find the first matching column (case-insensitive)."""
    cols_lower = {c.strip().lower(): c for c in df.columns}
    for alias in aliases:
        if alias in cols_lower:
            return cols_lower[alias]
    return None

def _extract_from_tables(tables: List[pd.DataFrame]) -> List[Dict]:
    """Stage 1: Extract transactions from structured DataFrames."""
    results = []
    for df in tables:
        if df is None or df.empty:
            continue
        
        # Map semantic columns
        date_col   = _find_column(df, COLUMN_ALIASES["date"])
        amt_col    = _find_column(df, COLUMN_ALIASES["amount"])
        debit_col  = _find_column(df, COLUMN_ALIASES["debit"])
        credit_col = _find_column(df, COLUMN_ALIASES["credit"])
        type_col   = _find_column(df, COLUMN_ALIASES["type"])
        desc_col   = _find_column(df, COLUMN_ALIASES["description"])

        if not date_col and not amt_col and not debit_col:
            logger.debug("[Stage1] Table has no recognizable financial columns — skipping")
            continue

        for _, row in df.iterrows():
            tx = _table_row_to_tx(row, date_col, amt_col, debit_col, credit_col, type_col, desc_col)
            if tx:
                results.append(tx)

    logger.info(f"[Stage1] Extracted {len(results)} transactions from {len(tables)} tables")
    return results


def _table_row_to_tx(row, date_col, amt_col, debit_col, credit_col, type_col, desc_col) -> Optional[Dict]:
    """Convert a single table row into a transaction dict."""
    # Date
    date_str = None
    if date_col and pd.notna(row.get(date_col)):
        dt = _parse_date(str(row[date_col]))
        if dt:
            date_str = dt.strftime("%Y-%m-%d")

    # Amount + Type
    amount = None
    tx_type = None

    # Separate debit/credit columns (e.g. SBI, HDFC format)
    if debit_col and credit_col:
        dr_raw = str(row.get(debit_col, "") or "").strip().replace(",", "")
        cr_raw = str(row.get(credit_col, "") or "").strip().replace(",", "")
        try:
            dr = float(dr_raw) if dr_raw and dr_raw not in ("", "nan", "-") else 0.0
        except ValueError:
            dr = 0.0
        try:
            cr = float(cr_raw) if cr_raw and cr_raw not in ("", "nan", "-") else 0.0
        except ValueError:
            cr = 0.0

        if dr > 0:
            amount, tx_type = dr, "debit"
        elif cr > 0:
            amount, tx_type = cr, "credit"

    # Single amount column
    if amount is None and amt_col and pd.notna(row.get(amt_col)):
        raw = str(row[amt_col]).replace(",", "").replace("₹", "").replace("Rs.", "").strip()
        try:
            val = float(raw)
            amount = abs(val)
            # If explicit type column exists, use it
            if type_col and pd.notna(row.get(type_col)):
                t_val = str(row[type_col]).strip().lower()
                if "cr" in t_val or "credit" in t_val:
                    tx_type = "credit"
                elif "dr" in t_val or "debit" in t_val:
                    tx_type = "debit"
            if not tx_type:
                tx_type = "credit" if val > 0 else "debit"
        except ValueError:
            pass

    # Description
    description = ""
    if desc_col and pd.notna(row.get(desc_col)):
        description = str(row[desc_col]).strip()

    # Field count
    fields_present = sum([date_str is not None, amount is not None, tx_type is not None, bool(description)])
    if fields_present < MIN_VALID_FIELDS:
        return None
    if amount == 0 or amount is None:
        return None

    return {
        "date": date_str or datetime.datetime.utcnow().strftime("%Y-%m-%d"),
        "amount": amount,
        "type": tx_type or "debit",
        "description": description or "Bank Transaction",
        "category": None,  # Will be filled in Stage 3
    }


# ─────────────────────────────────────────────
# STAGE 2 — REGEX HEURISTIC EXTRACTION (Bank-Routed)
# ─────────────────────────────────────────────

# —— Amount cleaning helper ——
def _clean_amount(raw: str) -> Optional[float]:
    """Parse amount string with commas/currency symbols. Returns None on failure."""
    cleaned = str(raw or "").replace(",", "").replace("₹", "").replace("Rs.", "").replace("INR", "").strip()
    try:
        val = float(re.sub(r"[^0-9.\-+]", "", cleaned))
        return val if val != 0 else None
    except (ValueError, TypeError):
        return None


# —— Bank Detection ——
BANK_SIGNATURES = {
    "sbi":   ["state bank of india", "sbi", "sbin"],
    "hdfc":  ["hdfc bank", "hdfcbank"],
    "icici": ["icici bank", "icicibank"],
    "axis":  ["axis bank", "axisbank"],
    "kotak": ["kotak mahindra", "kotak bank"],
    "yes":   ["yes bank"],
    "pnb":   ["punjab national bank", "pnb"],
}

def _detect_bank(text: str) -> str:
    """Detect bank from document header text."""
    text_lower = text[:500].lower()  # Only check header
    for bank, sigs in BANK_SIGNATURES.items():
        if any(sig in text_lower for sig in sigs):
            logger.info(f"[Stage2] Detected bank: {bank.upper()}")
            return bank
    return "generic"


# —— Bank-Specific Patterns ——

# SBI / Axis format: DD/MM/YY DESC [REF] DEBIT|CREDIT BALANCE
# Real SBI PDFs concatenate columns with single spaces — we match on the
# trailing pair (amount, balance) to avoid greedy desc eating amounts.
# Pattern: date \s+ anything \s+ (debit_or_credit) \s+ balance
PATTERN_SBI = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{2})\s+"
    r"(?P<desc>.+?)\s+"
    r"(?P<ref>[A-Za-z0-9/_\-]{6,20}\d)?\s*"     # Optional alphanumeric ref
    r"(?P<dr>[0-9]{1,3}(?:,[0-9]{2,3})*\.\d{2})?\s*"  # Optional DEBIT
    r"(?P<cr>[0-9]{1,3}(?:,[0-9]{2,3})*\.\d{2})?\s+"  # Optional CREDIT
    r"(?P<bal>[0-9]{1,3}(?:,[0-9]{2,3})*\.\d{2})$",   # Mandatory BALANCE at EOL
    re.IGNORECASE | re.MULTILINE,
)

# SBI CONDENSED: rows have only ONE amount before balance (debit or credit, infer from keywords)
# Matches: DD/MM/YY DESC [SOMETHING] AMOUNT BALANCE
PATTERN_SBI_CONDENSED = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{2})\s+"
    r"(?P<desc>.+?)\s+"
    r"(?P<amount>[0-9]{1,3}(?:,[0-9]{2,3})*\.\d{2})\s+"
    r"(?P<bal>[0-9]{1,3}(?:,[0-9]{2,3})*\.\d{2})$",
    re.IGNORECASE | re.MULTILINE,
)

# HDFC format: DD/MM/YYYY | NARRATION | CHQ/REF | VALUE DATE | WITHDRAWAL | DEPOSIT | CLOSING BALANCE
PATTERN_HDFC = re.compile(
    r"^(?P<date>\d{2}/\d{2}/\d{4})\s*"
    r"(?P<desc>.+?)\s{2,}"
    r"(?P<ref>[A-Za-z0-9/_\-]*)\s*"
    r"(?P<dr>[0-9,]+\.\d{2})?\s*"
    r"(?P<cr>[0-9,]+\.\d{2})?\s+"
    r"(?P<bal>[0-9,]+\.\d{2})",
    re.IGNORECASE | re.MULTILINE,
)


# ICICI/Kotak/Yes: Date | Description | Amount (+/-) | Balance
PATTERN_ICICI = re.compile(
    r"(?P<date>\d{2}[-/]\d{2}[-/]\d{2,4})\s+"
    r"(?P<desc>[A-Za-z0-9\s/\-_@#&*.,()]+?)\s{2,}"
    r"(?P<amount>[+-]?[0-9,]+\.\d{2})\s+"
    r"(?P<bal>[0-9,]+\.\d{2})",
    re.IGNORECASE,
)

# Generic: Date | Description | Amount
PATTERN_GENERIC_ISO = re.compile(
    r"(?P<date>\d{4}[-/]\d{2}[-/]\d{2})\s+"
    r"(?P<desc>[A-Za-z0-9\s/\-_@#&*.,()]{5,80}?)\s+"
    r"(?P<amount>[+-]?[0-9,]+\.\d{1,2})",
    re.IGNORECASE,
)

# Generic: DD/MM/YYYY Description Amount (single amount column)
PATTERN_GENERIC_DMY = re.compile(
    r"(?P<date>\d{2}[-/]\d{2}[-/]\d{4})\s+"
    r"(?P<desc>[A-Za-z0-9\s/\-_@#&*.,()]{5,80}?)\s+"
    r"(?P<amount>[+-]?[0-9,]+\.\d{1,2})",
    re.IGNORECASE,
)

# Keywords for type inference
DEBIT_KEYWORDS  = ["dr", "debit", "withdrawal", "paid", "purchase", "payment", "sent", "transfer out",
                   "upi/", "atm", "emi", "loan", "bill", "recharge", "subscription", "neft/out", "petrol", "cred_pay"]
CREDIT_KEYWORDS = ["cr", "credit", "deposit", "received", "salary", "refund", "cashback", "transfer in",
                   "int.pd", "interest", "reversal", "neft/in", "imps/in"]

BANK_PATTERN_MAP = {
    "sbi":     [(PATTERN_SBI, "sbi_multi_col"), (PATTERN_SBI_CONDENSED, "sbi_condensed")],
    "hdfc":    [(PATTERN_HDFC, "hdfc_multi_col"), (PATTERN_GENERIC_DMY, "hdfc_generic")],
    "icici":   [(PATTERN_ICICI, "icici_signed"), (PATTERN_GENERIC_DMY, "icici_generic")],
    "axis":    [(PATTERN_SBI, "axis_sbi_compat"), (PATTERN_SBI_CONDENSED, "axis_condensed"), (PATTERN_GENERIC_DMY, "axis_generic")],
    "kotak":   [(PATTERN_ICICI, "kotak_signed"), (PATTERN_GENERIC_DMY, "kotak_generic")],
    "yes":     [(PATTERN_ICICI, "yes_signed"), (PATTERN_GENERIC_DMY, "yes_generic")],
    "pnb":     [(PATTERN_SBI, "pnb_sbi_compat"), (PATTERN_SBI_CONDENSED, "pnb_condensed")],
    "generic": [(PATTERN_GENERIC_ISO, "generic_iso"), (PATTERN_GENERIC_DMY, "generic_dmy"), (PATTERN_ICICI, "generic_signed"), (PATTERN_SBI_CONDENSED, "generic_sbi_condensed")],
}


def _infer_type_from_context(line: str) -> str:
    line_lower = line.lower()
    if any(kw in line_lower for kw in CREDIT_KEYWORDS):
        return "credit"
    if any(kw in line_lower for kw in DEBIT_KEYWORDS):
        return "debit"
    return "debit"


def _row_from_match(m: re.Match, line: str) -> Optional[Dict]:
    """Parse a regex match into a transaction dict."""
    g = m.groupdict()

    # Description first — needed for early-exit keyword checks
    description = str(g.get("desc") or "").strip()
    if not description:
        description = re.sub(r"[\d,\.]+", "", line).strip()[:120]
    description = description[:255]

    # Skip balance/summary rows by description keyword
    SKIP_ROWS = ["opening balance", "closing balance", "total debit", "total credit",
                 "page ", "computer generated", "register for"]
    desc_lower = description.lower()
    if any(sk in desc_lower for sk in SKIP_ROWS):
        return None

    # Date
    date_str = None
    raw_date = g.get("date", "")
    if raw_date:
        dt = _parse_date(raw_date.strip())
        if dt:
            date_str = dt.strftime("%Y-%m-%d")

    # Amount: prefer separate Dr/Cr columns, then signed single amount
    amount: Optional[float] = None
    tx_type: Optional[str] = None

    has_dr_cr = "dr" in g and "cr" in g  # Both keys must exist in pattern group
    if has_dr_cr:
        dr_val = _clean_amount(g.get("dr"))
        cr_val = _clean_amount(g.get("cr"))
        # Strict: exactly one must be non-zero
        if dr_val and dr_val > 0 and not (cr_val and cr_val > 0):
            amount, tx_type = dr_val, "debit"
        elif cr_val and cr_val > 0 and not (dr_val and dr_val > 0):
            amount, tx_type = cr_val, "credit"
        elif dr_val and cr_val:
            # Both filled — use the one that makes contextual sense
            amount = max(dr_val, cr_val)
            tx_type = "debit" if dr_val >= cr_val else "credit"
    elif "amount" in g:
        val = _clean_amount(g.get("amount"))
        if val is not None:
            amount = abs(val)
            # Infer type from description keywords (matches verified SBI test)
            tx_type = _infer_type_from_context(description)

    # Skip if no amount (balance-only rows, headers, footers)
    if amount is None or amount <= 0:
        return None

    # Balance guard: amount == balance means it's an opening/closing balance row
    bal_val = _clean_amount(g.get("bal"))
    if bal_val and abs(bal_val - amount) < 0.01 and not has_dr_cr:
        return None

    fields = sum([date_str is not None, amount is not None, tx_type is not None, bool(description)])
    if fields < MIN_VALID_FIELDS:
        return None

    return {
        "date":        date_str or datetime.datetime.utcnow().strftime("%Y-%m-%d"),
        "amount":      amount,
        "type":        tx_type or "debit",
        "description": description or "Bank Transaction",
        "category":    None,
    }


def _extract_from_text(text: str) -> List[Dict]:
    """Stage 2: Bank-routed regex extraction with per-pattern logging."""
    if not text:
        return []

    bank = _detect_bank(text)
    patterns = BANK_PATTERN_MAP.get(bank, BANK_PATTERN_MAP["generic"])
    lines = text.split("\n")
    used_indices: set = set()
    results: List[Dict] = []
    pattern_hits: dict = {}

    for pattern, pattern_name in patterns:
        hits = 0
        for i, line in enumerate(lines):
            if i in used_indices or len(line.strip()) < 10:
                continue
            m = pattern.search(line)
            if not m:
                continue
            tx = _row_from_match(m, line)
            if tx:
                results.append(tx)
                used_indices.add(i)
                hits += 1
        pattern_hits[pattern_name] = hits
        logger.info(f"[Stage2] Pattern '{pattern_name}': {hits} transactions")

    logger.info(
        f"[Stage2] Bank={bank.upper()} Total={len(results)} "
        f"patterns_used={list(pattern_hits.keys())}"
    )
    return results


# ─────────────────────────────────────────────
# STAGE 3 — LLM CATEGORIZATION (NOT extraction)
# ─────────────────────────────────────────────
def _llm_categorize(transactions: List[Dict]) -> List[Dict]:
    """Stage 3: Use LLM only for categorization of already-extracted transactions."""
    if not transactions:
        return transactions

    # First apply keyword rules (free, fast)
    uncategorized = []
    for tx in transactions:
        cat = _keyword_category(tx.get("description", ""))
        if cat:
            tx["category"] = cat
        else:
            uncategorized.append(tx)

    if not uncategorized:
        logger.info("[Stage3] All transactions categorized via keyword rules — no LLM needed")
        return transactions

    # Build a compact prompt for remaining uncategorized ones
    items = [
        {"i": idx, "desc": tx.get("description", ""), "type": tx.get("type")}
        for idx, tx in enumerate(transactions)
        if tx.get("category") is None
    ]

    prompt = f"""You are a financial data categorizer. Categorize each transaction into ONE of these categories:
Food & Dining, Shopping, Travel, Subscriptions, Salary, EMI / Loans, Utilities, Rent / Housing, Healthcare, Cash, Investments, Tax, Insurance, Transfers, Miscellaneous.

Transactions (JSON):
{json.dumps(items[:50])}

Return ONLY a JSON array matching same indexes:
[{{"i": <index>, "category": "<category>"}}]
OUTPUT ONLY THE JSON ARRAY:"""

    try:
        content = call_llm(prompt, temperature=0.0)
        start = content.find("[")
        end = content.rfind("]") + 1
        if start != -1:
            cats = json.loads(content[start:end])
            for item in cats:
                idx = item.get("i")
                if idx is not None and 0 <= idx < len(transactions):
                    transactions[idx]["category"] = item.get("category", "Miscellaneous")
        logger.info(f"[Stage3] LLM categorized {len(items)} transactions")
    except Exception as e:
        logger.warning(f"[Stage3] LLM categorization failed ({e}) — using 'Miscellaneous'")
        for tx in transactions:
            if not tx.get("category"):
                tx["category"] = "Miscellaneous"

    return transactions


# ─────────────────────────────────────────────
# STAGE 4 — LLM FALLBACK EXTRACTION
# ─────────────────────────────────────────────
def _llm_extract_fallback(text: str) -> List[Dict]:
    """Stage 4: Full LLM extraction — only when Stages 1+2 both yield zero results."""
    if not text or not text.strip():
        return []

    # Performance guard
    safe_text = text[:MAX_TEXT_FOR_LLM]
    logger.info(f"[Stage4] LLM fallback extraction triggered — {len(safe_text)} chars sent")

    prompt = f"""You are a financial data extractor for bank statements.

TEXT:
\"\"\"{safe_text}\"\"\"

EXTRACT all financial transactions. Rules:
- Return a JSON array. Each element must have: "date" (YYYY-MM-DD), "amount" (positive number), "type" ("credit" or "debit"), "description" (text).
- Skip opening/closing balance rows.
- If a date is in DD/MM/YY or DD/MM/YYYY format, convert it to YYYY-MM-DD.
- If type is unclear, infer from context: withdrawals/payments are "debit", deposits/salary are "credit".
- Provide your best guess if unsure. Do NOT skip transactions.
- If no transactions exist in the text, return [].

Return ONLY the JSON array, nothing else:"""

    try:
        content = call_llm(prompt, temperature=0.0)
        logger.debug(f"[Stage4] LLM raw output: {content[:300]}")
        start = content.find("[")
        end = content.rfind("]") + 1
        if start == -1:
            logger.warning("[Stage4] LLM returned no JSON array")
            return []
        raw = json.loads(content[start:end])
        logger.info(f"[Stage4] LLM extracted {len(raw)} raw transactions")
        return raw
    except json.JSONDecodeError as e:
        logger.error(f"[Stage4] JSON parse error: {e}")
        return []
    except Exception as e:
        logger.error(f"[Stage4] LLM fallback failed: {e}")
        return []


# ─────────────────────────────────────────────
# TRANSACTION NORMALIZER
# ─────────────────────────────────────────────
def _normalize_tx(tx: Dict) -> Optional[Dict]:
    """Validate and normalize a raw transaction dict."""
    try:
        amt_raw = tx.get("amount", 0) or 0
        amt = float(str(amt_raw).replace(",", "").replace("₹", "").replace("Rs.", "").strip())
        if amt <= 0:
            return None

        dt_str = tx.get("date")
        if not dt_str:
            return None
        dt = _parse_date(str(dt_str))
        if not dt:
            return None

        desc = str(tx.get("description", "") or "Bank Transaction").strip()[:255]
        tx_type = str(tx.get("type", "debit") or "debit").lower()
        if tx_type not in ("credit", "debit"):
            tx_type = "debit"

        return {
            "date": dt,
            "date_str": dt.strftime("%Y-%m-%d"),
            "amount": abs(amt),
            "type": tx_type,
            "description": desc or "Bank Transaction",
            "category": tx.get("category") or "Miscellaneous",
        }
    except Exception:
        return None


def extract_bank_transactions(file_path: str, filename: str) -> Tuple[List[Dict], Dict]:
    """Extract, normalize, and categorize statement transactions for RAG ingestion."""
    doc = parse_document(file_path, filename)
    text = doc.get("text", "")
    tables = doc.get("tables", [])
    method = doc.get("method", "unknown")

    stage1_txs = _extract_from_tables(tables)
    stage2_txs = _extract_from_text(text) if len(stage1_txs) == 0 else []
    transactions = stage1_txs + stage2_txs
    fallback_triggered = False

    if not transactions:
        fallback_triggered = True
        transactions = _llm_extract_fallback(text)

    if transactions:
        transactions = _llm_categorize(transactions)

    normalized = []
    for tx in transactions:
        norm = _normalize_tx(tx)
        if norm:
            normalized.append(norm)

    metadata = {
        "text": text,
        "tables_count": len(tables),
        "method": method,
        "raw_count": len(transactions),
        "valid_count": len(normalized),
        "fallback_triggered": fallback_triggered,
    }
    return normalized, metadata


def transaction_to_semantic_text(tx: Dict) -> str:
    """Convert one structured transaction into the only text we embed for tx RAG."""
    amount = float(tx.get("amount", 0.0))
    category = tx.get("category") or "Miscellaneous"
    description = tx.get("description") or "Bank Transaction"
    date = tx.get("date_str") or tx.get("date")
    tx_type = tx.get("type", "debit")

    if tx_type == "credit":
        if category == "Salary":
            return f"Received ₹{amount:g} salary on {date}"
        return f"Received ₹{amount:g} for {description} ({category}) on {date}"
    return f"Spent ₹{amount:g} on {description} ({category}) on {date}"


def build_transaction_payloads(transactions: List[Dict], filename: str, user_id: Optional[int] = None) -> List[Dict]:
    """Build Qdrant payloads with structured metadata plus semantic text."""
    payloads = []
    for index, tx in enumerate(transactions):
        semantic_text = transaction_to_semantic_text(tx)
        tx_hash = tx.get("tx_hash") or _tx_hash(
            tx["date_str"],
            tx["amount"],
            tx["description"],
            index,
            user_id or 0,
        )
        payload = {
            "amount": tx["amount"],
            "category": tx.get("category") or "Miscellaneous",
            "date": tx["date_str"],
            "description": tx["description"],
            "type": tx.get("type", "debit"),
            "text": semantic_text,
            "semantic_text": semantic_text,
            "source_file": filename,
            "tx_hash": tx_hash,
        }
        if user_id is not None:
            payload["user_id"] = str(user_id)
        payloads.append(payload)
    return payloads


def build_financial_insights(transactions: List[Dict], user_id: Optional[int] = None) -> List[Tuple[str, Dict]]:
    """Create semantic insight records from structured transactions."""
    debits = [tx for tx in transactions if tx.get("type") == "debit"]
    credits = [tx for tx in transactions if tx.get("type") == "credit"]
    total_spend = sum(float(tx.get("amount", 0.0)) for tx in debits)
    total_income = sum(float(tx.get("amount", 0.0)) for tx in credits)

    category_totals: Dict[str, float] = {}
    for tx in debits:
        category = tx.get("category") or "Miscellaneous"
        category_totals[category] = category_totals.get(category, 0.0) + float(tx.get("amount", 0.0))

    insights: List[Tuple[str, Dict]] = []
    month = None
    dated = [tx for tx in transactions if tx.get("date")]
    if dated:
        first_date = dated[0]["date"]
        if isinstance(first_date, datetime.datetime):
            month = first_date.strftime("%B")

    period = month or "the uploaded statement"
    insights.append((f"Total spending in {period}: ₹{total_spend:g}", {"kind": "total_spend"}))
    insights.append((f"Total income in {period}: ₹{total_income:g}", {"kind": "total_income"}))

    if category_totals:
        top_category, top_amount = max(category_totals.items(), key=lambda item: item[1])
        insights.append((f"Top category: {top_category} (₹{top_amount:g})", {"kind": "top_category", "category": top_category}))

    if transactions:
        highest = max(transactions, key=lambda tx: float(tx.get("amount", 0.0)))
        insights.append((
            f"Highest transaction: ₹{float(highest['amount']):g} for {highest['description']} on {highest['date_str']}",
            {"kind": "highest_transaction"},
        ))

    enriched = []
    for text, metadata in insights:
        payload = {"type": "financial_insight", **metadata}
        if user_id is not None:
            payload["user_id"] = str(user_id)
        enriched.append((text, payload))
    return enriched


async def vectorize_financial_rag_async(
    transactions: List[Dict],
    filename: str,
    user_id: Optional[int] = None,
) -> Dict[str, int]:
    """Embed semantic transactions and derived insights, then upsert into Qdrant."""
    tx_payloads = build_transaction_payloads(transactions, filename, user_id=user_id)
    if not tx_payloads:
        return {"transactions": 0, "insights": 0}

    tx_embeddings = await generate_embeddings_async([payload["text"] for payload in tx_payloads])
    insert_transactions(tx_payloads, tx_embeddings)

    insight_count = 0
    for insight_text, metadata in build_financial_insights(transactions, user_id=user_id):
        embedding = (await generate_embeddings_async([insight_text]))[0]
        insert_insight(insight_text, metadata, embedding)
        insight_count += 1

    return {"transactions": len(tx_payloads), "insights": insight_count}


def vectorize_financial_rag(transactions: List[Dict], filename: str, user_id: Optional[int] = None) -> Dict[str, int]:
    """Synchronous wrapper for background activation jobs."""
    try:
        import asyncio
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import threading
        result = []

        def run_in_thread():
            result.append(asyncio.run(vectorize_financial_rag_async(transactions, filename, user_id=user_id)))

        thread = threading.Thread(target=run_in_thread)
        thread.start()
        thread.join()
        return result[0]

    import asyncio
    return asyncio.run(vectorize_financial_rag_async(transactions, filename, user_id=user_id))


# ─────────────────────────────────────────────
# DB SAVE
# ─────────────────────────────────────────────
def _save_transactions(db: Session, user_id: int, transactions: List[Dict]) -> Tuple[int, int]:
    """Save deduplicated transactions to DB. Returns (new_saved, valid_extracted)."""
    saved = 0
    valid_extracted = 0
    for i, tx in enumerate(transactions):
        norm = _normalize_tx(tx)
        if not norm:
            continue
        valid_extracted += 1
        tx_h = _tx_hash(norm["date_str"], norm["amount"], norm["description"], i, user_id)
        if db.query(Transaction).filter(
            Transaction.user_id == user_id,
            Transaction.tx_hash == tx_h
        ).first():
            continue  # Duplicate

        new_tx = Transaction(
            user_id=user_id,
            amount=norm["amount"],
            type=norm["type"],
            category=norm["category"],
            description=norm["description"],
            date=norm["date"],
            tx_hash=tx_h,
        )
        db.add(new_tx)
        saved += 1

        # Detect Bills
        if norm["category"] in ("Utilities", "Rent / Housing", "Subscriptions") or "subscription" in norm["description"].lower():
            db.add(Bill(
                user_id=user_id,
                name=norm["description"][:255],
                amount=norm["amount"],
                due_date=norm["date"] + datetime.timedelta(days=30),
                status="paid"
            ))

        # Detect Loans
        if norm["category"] == "EMI / Loans" or "emi" in norm["description"].lower():
            db.add(Loan(
                user_id=user_id,
                loan_type="Detected Loan",
                total_amount=norm["amount"] * 12,
                remaining_amount=norm["amount"] * 6,
                emi=norm["amount"],
                interest_rate=12.0,
                status="active"
            ))

    db.commit()
    return saved, valid_extracted


# ─────────────────────────────────────────────
# SUMMARY COMPUTATION
# ─────────────────────────────────────────────
def _build_summary(db: Session, user, raw_txs: List[Dict]) -> None:
    """Recompute and save UserFinancialSummary."""
    credits = [tx["amount"] for tx in raw_txs if tx.get("type") == "credit"]
    debits  = [tx["amount"] for tx in raw_txs if tx.get("type") == "debit"]

    monthly_income = sum(
        tx["amount"] for tx in raw_txs
        if tx.get("type") == "credit" and tx.get("category") == "Salary"
    )
    monthly_spend   = sum(debits)
    total_balance   = sum(credits) - sum(debits)
    emi_total       = sum(tx["amount"] for tx in raw_txs if tx.get("category") == "EMI / Loans")
    savings         = max(0.0, total_balance * 0.2)

    # Category distribution
    cat_dist: Dict[str, float] = {}
    for tx in raw_txs:
        cat = tx.get("category", "Miscellaneous")
        cat_dist[cat] = cat_dist.get(cat, 0.0) + tx.get("amount", 0.0)

    user.monthly_income = monthly_income

    summary = db.query(UserFinancialSummary).filter_by(user_id=user.id).first()
    if not summary:
        summary = UserFinancialSummary(user_id=user.id)
        db.add(summary)

    summary.total_balance        = total_balance
    summary.monthly_income       = monthly_income
    summary.monthly_spend        = monthly_spend
    summary.emi_total            = emi_total
    summary.savings              = savings
    summary.income_detected      = monthly_income
    summary.category_distribution = json.dumps(cat_dist)
    summary.last_upload_date     = datetime.datetime.utcnow()
    summary.last_updated         = datetime.datetime.utcnow()
    db.commit()

    # Derived Insight Generation for Vector Store
    try:
        month_str = datetime.datetime.utcnow().strftime("%B %Y")
        top_cat = max(cat_dist.items(), key=lambda x: x[1])[0] if cat_dist else "None"
        top_cat_amt = cat_dist.get(top_cat, 0.0)
        
        insight_text = (
            f"In {month_str}, user spent ₹{monthly_spend:,.2f}. "
            f"Top category: {top_cat} (₹{top_cat_amt:,.2f}). "
            f"Monthly income detected: ₹{monthly_income:,.2f}. "
            f"Total balance across detected accounts is ₹{total_balance:,.2f}."
        )
        
        logger.info(f"Generated insight: {insight_text}")
        
        # Embed and store insight
        embedding = generate_embeddings([insight_text])[0]
        insert_insight(
            insight_text=insight_text,
            metadata={"user_id": str(user.id), "month": month_str, "type": "monthly_summary"},
            embedding=embedding
        )
    except Exception as e:
        logger.error(f"Failed to embed insights: {e}")



# ─────────────────────────────────────────────
# PUBLIC ENTRY POINTS
# ─────────────────────────────────────────────
def process_upload_safe(user_id: str, file_path: str, filename: str):
    """Wrapper to catch errors in background tasks."""
    db = SessionLocal()
    try:
        data_activation_pipeline(db, user_id, file_path, filename)
    except Exception as e:
        logger.error(f"[Pipeline] Fatal error for user {user_id}: {e}", exc_info=True)
        user = get_user_by_external_id(db, user_id)
        if user:
            status = db.query(UserProcessingStatus).filter_by(user_id=user.id).first()
            if status:
                status.status = "failed"
                status.error_message = f"Unexpected error: {str(e)[:500]}"
                db.commit()
    finally:
        db.close()


def data_activation_pipeline(db: Session, external_id: str, file_path: str, filename: str):
    user = get_user_by_external_id(db, external_id)
    if not user:
        raise ValueError("User not found")

    # ── Init Status ──────────────────────────
    status = db.query(UserProcessingStatus).filter_by(user_id=user.id).first()
    if not status:
        status = UserProcessingStatus(user_id=user.id)
        db.add(status)

    def _update(progress: int, stage: str):
        status.status   = "processing"
        status.progress = progress
        status.stage    = stage
        db.commit()
        logger.info(f"[Pipeline] {progress}% — {stage}")

    _update(10, "Parsing document...")

    # ── Parse Document ───────────────────────
    doc = parse_document(file_path, filename)
    text   = doc["text"]
    tables = doc.get("tables", [])
    method = doc.get("method", "unknown")
    logger.info(f"[Pipeline] File='{filename}' method={method} text_len={len(text)} tables={len(tables)}")

    _update(25, f"Extraction method: {method}")

    # ── Stage 1: Structured Tables ───────────
    _update(30, "Stage 1: Structured table extraction...")
    stage1_txs = _extract_from_tables(tables)
    logger.info(f"[Pipeline] Stage 1 result: {len(stage1_txs)} transactions")

    # ── Stage 2: Regex Heuristics ────────────
    _update(45, "Stage 2: Regex heuristic extraction...")
    stage2_txs = _extract_from_text(text) if len(stage1_txs) == 0 else []
    logger.info(f"[Pipeline] Stage 2 result: {len(stage2_txs)} transactions")

    combined = stage1_txs + stage2_txs
    fallback_triggered = False

    # ── Stage 4: LLM Fallback Extraction ─────
    if len(combined) == 0:
        _update(55, "Stage 4: LLM fallback extraction (structured parsing found 0 results)...")
        fallback_triggered = True
        combined = _llm_extract_fallback(text)
        logger.info(f"[Pipeline] Stage 4 result: {len(combined)} transactions")

    # ── Stage 3: LLM Categorization ──────────
    if combined:
        _update(65, "Stage 3: Categorizing transactions...")
        combined = _llm_categorize(combined)

    _update(75, "Deduplicating and saving...")

    # ── Save to DB ───────────────────────────
    new_saved, valid_extracted = _save_transactions(db, user.id, combined)
    total_raw   = len(combined)
    confidence  = valid_extracted / total_raw if total_raw > 0 else 0.0

    logger.info(
        f"[Pipeline] Done — raw={total_raw} valid={valid_extracted} new_saved={new_saved} "
        f"confidence={confidence:.2f} fallback={fallback_triggered}"
    )

    _update(90, "Computing financial summary and insights...")

    _build_summary(db, user, combined)
    
    _update(95, "Vectorizing transactions for knowledge base...")
    try:
        normalized_for_rag = []
        for tx in combined:
            norm = _normalize_tx(tx)
            if norm:
                normalized_for_rag.append(norm)
        vector_counts = vectorize_financial_rag(normalized_for_rag, filename, user_id=user.id)
        logger.info(
            "Financial RAG vectorization complete: transactions=%s insights=%s",
            vector_counts["transactions"],
            vector_counts["insights"],
        )
            
    except Exception as e:
        logger.error(f"Failed to vectorize transactions: {e}")

    # ── Final Outcome ─────────────────────────
    if valid_extracted == 0:
        status.status        = "failed"
        status.error_message = "No financial data detected in file. Please upload a valid bank statement."
        db.commit()
        logger.warning(f"[Pipeline] No transactions extracted from '{filename}'")
        return

    # Build summary from all DB transactions (not just this upload batch)
    all_db_txs = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    all_txs_dict = [
        {"amount": t.amount, "type": t.type, "category": t.category, "description": t.description}
        for t in all_db_txs
    ]
    _build_summary(db, user, all_txs_dict)

    # Confidence warning tag
    confidence_tag = ""
    if confidence < LOW_CONFIDENCE_THRESHOLD and not fallback_triggered:
        confidence_tag = f" (low confidence: {confidence:.0%})"

    status.status   = "completed"
    status.progress = 100
    status.stage    = (
        f"Activation complete — {valid_extracted} valid transactions handled{confidence_tag}. "
        f"{'Upload more data for better insights.' if valid_extracted < 10 else ''}"
    )
    db.commit()
    logger.info(f"[Pipeline] ✅ Completed '{filename}' — {valid_extracted} transactions extracted, {new_saved} newly saved")

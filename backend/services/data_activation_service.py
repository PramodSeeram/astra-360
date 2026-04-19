"""
Data Activation Service — Astra 360
4-Stage fallback-driven ingestion pipeline:
  Stage 1 → Structured table extraction (CSV/Excel/PDF tables via pandas)
  Stage 2 → Regex heuristic extraction (from raw text, multi-bank patterns)
  Stage 3 → Hybrid categorization: rules/cache first, AI fallback only for unknowns
  Stage 4 → LLM fallback extraction (only if stages 1+2 both yield 0 results)
"""

import os
import re
import json
import asyncio
import logging
import datetime
import hashlib
import random
from collections import Counter, defaultdict
import pandas as pd
import httpx
from typing import List, Dict, Tuple, Optional
from sqlalchemy.orm import Session

from database import SessionLocal
from models import (
    User, Transaction, Bill, Loan, UserFinancialSummary,
    Subscription, Card, CalendarEvent,
    UserProcessingStatus, get_user_by_external_id
)
from rag.document_processor import parse_document
from rag.embeddings import generate_embeddings
from rag.vector_store import (
    COLLECTION_INSIGHTS,
    COLLECTION_TRANSACTIONS,
    upsert_knowledge_points,
)
from services.llm_service import call_llm, get_llm_model, get_llm_url, get_ollama_headers, LLM_TIMEOUT
from services.financial_engine import (
    _EMI_IN_DESC,
    _RENT_IN_DESC,
    canonical_year_month,
    compute_snapshot_from_transactions,
)
from services.brain_insights_service import upsert_user_insights
from services.financial_cleanup import delete_user_financial_data

logger = logging.getLogger(__name__)


def _other_to_bills_from_narration(description: Optional[str], standardized: str) -> str:
    """If the LLM yields Other, map obvious rent/EMI narrations to Bills."""
    if standardized != "Other":
        return standardized
    text = str(description or "")
    if _RENT_IN_DESC.search(text) or _EMI_IN_DESC.search(text):
        return "Bills"
    return standardized

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
MIN_VALID_FIELDS = 3          # Accept partial records with at least 3 of 4 fields
MAX_TEXT_FOR_LLM  = 4000      # Performance guard — truncate before sending to LLM
LOW_CONFIDENCE_THRESHOLD = 0.3


# ─────────────────────────────────────────────
# HYBRID TRANSACTION CATEGORIZATION
# ─────────────────────────────────────────────
STANDARD_CATEGORIES = (
    "Food",
    "Shopping",
    "Transport",
    "Utilities",
    "Bills",
    "Transfers",
    "Entertainment",
    "Other",
)

CATEGORY_MAP = {
    "swiggy": "Food",
    "zomato": "Food",
    "amazon": "Shopping",
    "flipkart": "Shopping",
    "uber": "Transport",
    "ola": "Transport",
    "electricity": "Utilities",
    "netflix": "Entertainment",
}

CATEGORY_CACHE: Dict[str, str] = {}
CATEGORY_TIMEOUT_SECONDS = float(os.getenv("CATEGORY_TIMEOUT_SECONDS", "15"))
CATEGORY_CONCURRENCY = int(os.getenv("CATEGORY_CONCURRENCY", "5"))

_CATEGORY_PROMPT = (
    "Categorize this transaction into one of: "
    "Food, Shopping, Transport, Utilities, Bills, Transfers, Entertainment, Other. "
    "Transaction: {description}. Return only category."
)
_PAYMENT_PREFIX_RE = re.compile(r"\b(?:UPI|NEFT|IMPS|RTGS)\b[-/:]*", re.IGNORECASE)
_STRONG_TRANSFER_RE = re.compile(
    r"\b(?:neft|imps|rtgs|self transfer|fund transfer|account transfer|transfer to|transfer from)\b",
    re.IGNORECASE,
)


def clean_description(description: str) -> str:
    """Normalize noisy bank descriptions before categorization."""
    desc = str(description or "")
    desc = _PAYMENT_PREFIX_RE.sub(" ", desc)
    desc = re.sub(r"\d+", " ", desc)
    desc = desc.lower()
    desc = re.sub(r"[^a-z\s&]", " ", desc)
    return re.sub(r"\s+", " ", desc).strip()


def _cache_keys(description: str, cleaned: str) -> List[str]:
    raw = str(description or "").strip()
    keys = [raw]
    if raw.lower() not in keys:
        keys.append(raw.lower())
    if cleaned and cleaned not in keys:
        keys.append(cleaned)
    return [key for key in keys if key]


def _standardize_category(category: str) -> str:
    text = str(category or "").strip().splitlines()[0]
    normalized = re.sub(r"[^a-zA-Z &/]", " ", text).lower()
    normalized = re.sub(r"\s+", " ", normalized).strip()

    exact = {category.lower(): category for category in STANDARD_CATEGORIES}
    if normalized in exact:
        return exact[normalized]

    aliases = [
        (("transfer", "neft", "imps", "rtgs", "upi transfer", "self transfer"), "Transfers"),
        (("food", "dining", "restaurant", "restaurants", "grocery", "groceries"), "Food"),
        (("shop", "shopping", "retail", "ecommerce", "e commerce", "purchase"), "Shopping"),
        (("transport", "transportation", "travel", "cab", "taxi", "ride"), "Transport"),
        (("utility", "utilities", "electricity", "water", "gas", "broadband"), "Utilities"),
        (("bill", "bills", "emi", "loan", "rent", "insurance", "premium"), "Bills"),
        (("entertainment", "subscription", "subscriptions", "streaming", "ott", "movie"), "Entertainment"),
        (("other", "misc", "miscellaneous", "unknown"), "Other"),
    ]
    for needles, value in aliases:
        if any(needle in normalized for needle in needles):
            return value
    return "Other"


def rule_categorize(description: str) -> Optional[str]:
    desc = clean_description(description)
    for key, value in CATEGORY_MAP.items():
        if key in desc:
            return value
    return None


def _keyword_category(description: str) -> Optional[str]:
    """Backward-compatible alias for the fast rule classifier."""
    return rule_categorize(description)


def _cached_or_rule_category(description: str, cleaned: str) -> Optional[str]:
    for key in _cache_keys(description, cleaned):
        if key in CATEGORY_CACHE:
            return CATEGORY_CACHE[key]

    category = rule_categorize(cleaned)
    if not category and _STRONG_TRANSFER_RE.search(str(description or "")):
        category = "Transfers"

    if category:
        category = _standardize_category(category)
        _store_category(description, cleaned, category)
        return category
    return None


def _store_category(description: str, cleaned: str, category: str) -> None:
    standardized = _standardize_category(category)
    for key in _cache_keys(description, cleaned):
        CATEGORY_CACHE[key] = standardized


async def ai_categorize(description: str, semaphore: Optional[asyncio.Semaphore] = None) -> str:
    async def _request() -> str:
        payload = {
            "model": get_llm_model(),
            "prompt": _CATEGORY_PROMPT.format(description=description),
            "stream": False,
            "options": {"num_predict": 128, "temperature": 0.0},
        }
        try:
            async with httpx.AsyncClient(timeout=LLM_TIMEOUT) as client:
                response = await client.post(
                    get_llm_url(),
                    json=payload,
                    headers=get_ollama_headers(),
                )
                response.raise_for_status()
                return _standardize_category(response.json().get("response", ""))
        except (httpx.TimeoutException, httpx.HTTPError, ValueError) as e:
            logger.warning("[Stage3] AI categorization failed for '%s': %s", description[:80], e)
            return "Other"

    if semaphore:
        async with semaphore:
            return await _request()
    return await _request()


def _ai_categorize_sync(description: str) -> str:
    payload = {
        "model": get_llm_model(),
        "prompt": _CATEGORY_PROMPT.format(description=description),
        "stream": False,
        "options": {"num_predict": 128, "temperature": 0.0},
    }
    try:
        with httpx.Client(timeout=LLM_TIMEOUT) as client:
            response = client.post(
                get_llm_url(),
                json=payload,
                headers=get_ollama_headers(),
            )
            response.raise_for_status()
            return _standardize_category(response.json().get("response", ""))
    except (httpx.TimeoutException, httpx.HTTPError, ValueError) as e:
        logger.warning("[Stage3] Sync AI categorization failed for '%s': %s", description[:80], e)
        return "Other"


async def categorize_transaction_async(
    description: str,
    semaphore: Optional[asyncio.Semaphore] = None,
) -> str:
    cleaned = clean_description(description)
    category = _cached_or_rule_category(description, cleaned)
    if not category:
        category = await ai_categorize(cleaned or str(description or ""), semaphore=semaphore)
        _store_category(description, cleaned, category)
    final = _standardize_category(category)
    resolved = _other_to_bills_from_narration(description, final)
    if resolved != final:
        _store_category(description, cleaned, resolved)
    return resolved


def categorize_transaction(description: str) -> str:
    cleaned = clean_description(description)
    category = _cached_or_rule_category(description, cleaned)
    if not category:
        ai_input = cleaned or str(description or "")
        try:
            asyncio.get_running_loop()
            category = _ai_categorize_sync(ai_input)
        except RuntimeError:
            category = asyncio.run(ai_categorize(ai_input))
        _store_category(description, cleaned, category)
    final = _standardize_category(category)
    resolved = _other_to_bills_from_narration(description, final)
    if resolved != final:
        _store_category(description, cleaned, resolved)
    return resolved


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
    "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y",
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


def is_valid_bill(description: str) -> bool:
    keywords = ["electricity", "water", "rent", "gas", "internet", "mobile"]
    desc = (description or "").lower()
    return any(keyword in desc for keyword in keywords)


def _normalize_bill_name(description: str) -> str:
    desc = (description or "").strip()
    compact = re.sub(r"\s+", " ", desc).lower()
    replacements = {
        "elec": "electricity",
        "wifi": "internet",
        "broadband": "internet",
        "phone": "mobile",
        "postpaid": "mobile",
    }
    for source, target in replacements.items():
        compact = compact.replace(source, target)
    if "electricity" in compact:
        return "Electricity Bill"
    if "water" in compact:
        return "Water Bill"
    if "rent" in compact:
        return "Rent"
    if "gas" in compact:
        return "Gas Bill"
    if "internet" in compact:
        return "Internet Bill"
    if "mobile" in compact:
        return "Mobile Bill"
    return desc[:255] or "Utility Bill"

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
    "balance":     ["balance", "closing balance", "running balance", "available balance", "bal", "closing bal"],
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
        bal_col    = _find_column(df, COLUMN_ALIASES["balance"])

        if not date_col and not amt_col and not debit_col:
            logger.debug("[Stage1] Table has no recognizable financial columns — skipping")
            continue

        for _, row in df.iterrows():
            tx = _table_row_to_tx(row, date_col, amt_col, debit_col, credit_col, type_col, desc_col, bal_col)
            if tx:
                results.append(tx)

    logger.info(f"[Stage1] Extracted {len(results)} transactions from {len(tables)} tables")
    return results


def _table_row_to_tx(row, date_col, amt_col, debit_col, credit_col, type_col, desc_col, bal_col=None) -> Optional[Dict]:
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

    tx_type = _force_type_from_description(description, tx_type)

    # Field count
    fields_present = sum([date_str is not None, amount is not None, tx_type is not None, bool(description)])
    if fields_present < MIN_VALID_FIELDS:
        return None
    if amount == 0 or amount is None:
        return None

    if not date_str:
        return None

    balance: Optional[float] = None
    if bal_col and pd.notna(row.get(bal_col)):
        balance = _clean_amount(str(row[bal_col]))

    return {
        "date": date_str,
        "amount": amount,
        "type": tx_type or "debit",
        "description": description or "Bank Transaction",
        "category": None,  # Will be filled in Stage 3
        "balance": balance,
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
SALARY_DESCRIPTION_HINTS = ("salary", "payroll", "cms/salary")

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


def _force_type_from_description(description: str, inferred_type: Optional[str]) -> Optional[str]:
    """Deterministic override for semantically obvious credits/debits."""
    desc = (description or "").lower()
    if any(hint in desc for hint in SALARY_DESCRIPTION_HINTS):
        return "credit"
    return inferred_type


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

    tx_type = _force_type_from_description(description, tx_type)

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

    if not date_str:
        return None

    return {
        "date":        date_str,
        "amount":      amount,
        "type":        tx_type or "debit",
        "description": description or "Bank Transaction",
        "category":    None,
        "balance":     bal_val,
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
# STAGE 3 — HYBRID CATEGORIZATION (rules → cache → AI fallback)
# ─────────────────────────────────────────────
async def _categorize_transactions_async(transactions: List[Dict]) -> List[Dict]:
    """Stage 3: fast rules first, cached reuse second, AI only for unknowns."""
    if not transactions:
        return transactions

    semaphore = asyncio.Semaphore(max(1, CATEGORY_CONCURRENCY))
    categories = await asyncio.gather(
        *[
            categorize_transaction_async(tx.get("description", ""), semaphore=semaphore)
            for tx in transactions
        ]
    )
    for tx, category in zip(transactions, categories):
        tx["category"] = category

    logger.info(
        "[Stage3] Hybrid categorized %s transactions; cache_size=%s",
        len(transactions),
        len(CATEGORY_CACHE),
    )
    return transactions


def _categorize_transactions_sync(transactions: List[Dict]) -> List[Dict]:
    if not transactions:
        return transactions

    for tx in transactions:
        tx["category"] = categorize_transaction(tx.get("description", ""))

    logger.info(
        "[Stage3] Hybrid categorized %s transactions synchronously; cache_size=%s",
        len(transactions),
        len(CATEGORY_CACHE),
    )
    return transactions


def _llm_categorize(transactions: List[Dict]) -> List[Dict]:
    """Backward-compatible entrypoint for Stage 3 categorization."""
    if not transactions:
        return transactions

    try:
        asyncio.get_running_loop()
        return _categorize_transactions_sync(transactions)
    except RuntimeError:
        return asyncio.run(_categorize_transactions_async(transactions))


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

        bal_raw = tx.get("balance")
        balance: Optional[float] = None
        if bal_raw is not None and str(bal_raw).strip() not in ("", "nan", "None"):
            try:
                balance = float(str(bal_raw).replace(",", "").replace("₹", "").replace("Rs.", "").strip())
            except (ValueError, TypeError):
                balance = None

        return {
            "date": dt,
            "date_str": dt.strftime("%Y-%m-%d"),
            "amount": abs(amt),
            "type": tx_type,
            "description": desc or "Bank Transaction",
            "category": _standardize_category(tx.get("category") or "Other"),
            "balance": balance,
        }
    except Exception:
        return None


def _dedupe_raw_transactions(transactions: List[Dict]) -> List[Dict]:
    """Deduplicate parsed rows by (date, rounded amount, normalized description)."""
    seen: set = set()
    deduped: List[Dict] = []
    for tx in transactions:
        date_val = tx.get("date")
        if isinstance(date_val, datetime.datetime):
            date_key = date_val.strftime("%Y-%m-%d")
        else:
            date_key = str(date_val or "")
        amount_key = round(float(tx.get("amount") or 0.0), 2)
        desc_key = _normalize(tx.get("description", ""))[:40]
        type_key = (tx.get("type") or "").lower()
        key = (date_key, amount_key, desc_key, type_key)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(tx)
    return deduped


async def extract_bank_transactions_async(file_path: str, filename: str) -> Tuple[List[Dict], Dict]:
    """Async extraction path for API handlers that can await AI categorization."""
    doc = parse_document(file_path, filename)
    text = doc.get("text", "")
    tables = doc.get("tables", [])
    method = doc.get("method", "unknown")

    stage1_txs = _extract_from_tables(tables)
    stage2_txs = _extract_from_text(text)
    transactions = _dedupe_raw_transactions(stage1_txs + stage2_txs)
    logger.info(
        f"[Extract] stage1={len(stage1_txs)} stage2={len(stage2_txs)} merged={len(transactions)}"
    )
    fallback_triggered = False

    if not transactions:
        fallback_triggered = True
        transactions = _llm_extract_fallback(text)

    if transactions:
        transactions = await _categorize_transactions_async(transactions)

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


def extract_bank_transactions(file_path: str, filename: str) -> Tuple[List[Dict], Dict]:
    """Extract, normalize, and categorize statement transactions for RAG ingestion."""
    doc = parse_document(file_path, filename)
    text = doc.get("text", "")
    tables = doc.get("tables", [])
    method = doc.get("method", "unknown")

    stage1_txs = _extract_from_tables(tables)
    stage2_txs = _extract_from_text(text)
    transactions = _dedupe_raw_transactions(stage1_txs + stage2_txs)
    logger.info(
        f"[Extract] stage1={len(stage1_txs)} stage2={len(stage2_txs)} merged={len(transactions)}"
    )
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
    category = _standardize_category(tx.get("category") or "Other")
    description = tx.get("description") or "Bank Transaction"
    date = tx.get("date_str") or tx.get("date")
    tx_type = tx.get("type", "debit")

    if tx_type == "credit":
        if any(term in description.lower() for term in ("salary", "payroll", "employer")):
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
            "category": _standardize_category(tx.get("category") or "Other"),
            "date": tx["date_str"],
            "description": tx["description"],
            "type": tx.get("type", "debit"),
            "text": semantic_text,
            "semantic_text": semantic_text,
            "source": f"tx::{filename}",
            "source_file": filename,
            "chunk_index": index,
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
        category = _standardize_category(tx.get("category") or "Other")
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


def vectorize_financial_rag(
    transactions: List[Dict],
    filename: str,
    user_id: Optional[int] = None,
) -> Dict[str, int]:
    """Embed user-scoped transactions and insights into Qdrant.

    Returns accurate ``{transactions, insights}`` insert counts. Realtime
    chat insights are served from the DB snapshot (see
    ``services.user_context_service``) so a Qdrant failure here never
    breaks the chat path — it only reduces semantic recall.
    """

    tx_payloads = build_transaction_payloads(transactions, filename, user_id=user_id)
    tx_inserted = 0
    insight_inserted = 0

    if tx_payloads:
        try:
            tx_embeddings = generate_embeddings([payload["text"] for payload in tx_payloads])
            if tx_embeddings:
                tx_inserted = upsert_knowledge_points(
                    tx_payloads,
                    tx_embeddings,
                    collection_name=COLLECTION_TRANSACTIONS,
                )
        except Exception as exc:
            logger.warning("Transaction vectorization skipped: %s", exc)

    try:
        insight_rows = build_financial_insights(transactions, user_id=user_id)
    except Exception as exc:
        logger.warning("Insight synthesis failed: %s", exc)
        insight_rows = []

    if insight_rows:
        insight_chunks: List[Dict] = []
        insight_texts: List[str] = []
        for index, (insight_text, metadata) in enumerate(insight_rows):
            if not insight_text:
                continue
            insight_texts.append(insight_text)
            insight_chunks.append(
                {
                    "source": f"insight::{filename}",
                    "category": "finance",
                    "chunk_index": index,
                    "text": insight_text,
                    **metadata,
                }
            )
        if insight_chunks:
            try:
                embeddings = generate_embeddings(insight_texts)
                if embeddings:
                    insight_inserted = upsert_knowledge_points(
                        insight_chunks,
                        embeddings,
                        collection_name=COLLECTION_INSIGHTS,
                    )
            except Exception as exc:
                logger.warning("Insight vectorization skipped: %s", exc)

    return {"transactions": tx_inserted, "insights": insight_inserted}


async def vectorize_financial_rag_async(
    transactions: List[Dict],
    filename: str,
    user_id: Optional[int] = None,
) -> Dict[str, int]:
    """Async shim that runs the sync path off the event loop."""
    return await asyncio.to_thread(
        vectorize_financial_rag, transactions, filename, user_id
    )


# ─────────────────────────────────────────────
# DB SAVE
# ─────────────────────────────────────────────
# Merchant buckets for realistic demo card attribution. Each list maps to a
# position in the ordered card pool (card_1, card_2, card_3...).
MERCHANT_CARD_BUCKETS: Tuple[Tuple[str, ...], ...] = (
    ("amazon",),
    ("swiggy", "zomato"),
    ("netflix", "spotify"),
)


def _resolve_card_id(
    description: str, card_ids: List[int], user_id: int
) -> Optional[int]:
    """Pick a card for a debit based on merchant rules, else deterministic fallback."""
    if not card_ids:
        return None
    desc = (description or "").lower()
    for index, keywords in enumerate(MERCHANT_CARD_BUCKETS):
        if index >= len(card_ids):
            break
        if any(keyword in desc for keyword in keywords):
            return card_ids[index]
    seed_key = f"{user_id}|{clean_description(description)}"
    rng = random.Random(hashlib.md5(seed_key.encode()).hexdigest())
    return rng.choice(card_ids)


def _save_transactions(db: Session, user_id: int, transactions: List[Dict]) -> Tuple[int, int]:
    """Save deduplicated transactions to DB. Returns (new_saved, valid_extracted)."""
    saved = 0
    valid_extracted = 0

    user_cards = db.query(Card).filter(Card.user_id == user_id).order_by(Card.id.asc()).all()
    card_ids = [c.id for c in user_cards]

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

        assigned_card_id: Optional[int] = None
        if norm["type"] == "debit":
            assigned_card_id = _resolve_card_id(norm["description"], card_ids, user_id)

        new_tx = Transaction(
            user_id=user_id,
            amount=norm["amount"],
            type=norm["type"],
            category=norm["category"],
            description=norm["description"],
            date=norm["date"],
            tx_hash=tx_h,
            statement_balance=norm.get("balance"),
            card_id=assigned_card_id,
        )
        db.add(new_tx)
        saved += 1

    db.commit()
    # Bills, subscriptions, and loans are rebuilt from recurrence analysis in
    # _refresh_detected_commitments so we don't generate one-shot artifacts here.
    return saved, valid_extracted


def _backfill_card_assignments(db: Session, user_id: int) -> None:
    """Assign card_id by merchant rules (deterministic fallback) for any debit lacking one."""
    cards = db.query(Card).filter(Card.user_id == user_id).order_by(Card.id.asc()).all()
    if not cards:
        return
    unassigned = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.type == "debit",
            Transaction.card_id.is_(None),
        )
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    if not unassigned:
        return
    card_ids = [c.id for c in cards]
    for tx in unassigned:
        tx.card_id = _resolve_card_id(tx.description or "", card_ids, user_id)
    db.commit()


# Words that add noise across bank narrations (rails, geography, generic labels) — not merchant brands.
_RECURRENCE_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "from",
        "with",
        "to",
        "of",
        "on",
        "at",
        "by",
        "in",
        "upi",
        "inr",
        "dr",
        "cr",
        "txn",
        "ref",
        "id",
        "no",
        "dt",
        "val",
        "com",
        "co",
        "net",
        "org",
        "www",
        "pay",
        "payment",
        "paid",
        "india",
        "mumbai",
        "delhi",
        "bangalore",
        "bengaluru",
        "chennai",
        "hyderabad",
        "pune",
        "kolkata",
        "debit",
        "credit",
        "transfer",
        "neft",
        "imps",
        "rtgs",
        "nach",
        "subscription",
        "subscriptions",
        "billing",
        "monthly",
        "annual",
        "yearly",
        "auto",
        "standing",
        "instruction",
        "mandate",
    }
)

# Payment-type tokens (not merchant names): keep full token set when present so
# "house rent" does not collapse to "house" via the single-token shortcut.
_RECURRENCE_FIN_ANCHOR = frozenset(
    {"rent", "lease", "emi", "loan", "electricity", "water", "gas", "utility", "utilities"}
)

_COMMITMENT_HINT_SUB = re.compile(
    r"\b(subscription|streaming|ott|renewal|membership)\b",
    re.IGNORECASE,
)
_COMMITMENT_HINT_BILL = re.compile(
    r"\b("
    r"emi|nach|ecs|mortgage|"
    r"rent|lease|landlord|tenant|housing|"
    r"electricity|water|gas|utility|utilities|power"
    r")\b",
    re.IGNORECASE,
)
_LOAN_WORD = re.compile(r"\bloan\b", re.IGNORECASE)


def _recurrence_group_key(description: str) -> str:
    """Cluster similar narrations without merchant-specific lists: normalize, drop noise, sort tokens."""
    base = clean_description(description)
    if not base:
        return ""
    tokens = [t for t in base.split() if len(t) >= 3 and t not in _RECURRENCE_STOPWORDS]
    if not tokens:
        tokens = [t for t in base.split() if len(t) >= 2]
    if not tokens:
        return base[:160].strip()

    if frozenset(tokens) & _RECURRENCE_FIN_ANCHOR:
        tokens.sort()
        return " ".join(tokens)

    long_tokens = [t for t in tokens if len(t) >= 5]
    if len(tokens) >= 2 and len(long_tokens) == 1:
        return long_tokens[0]

    tokens.sort()
    return " ".join(tokens)


def _mode_category(categories: List[str]) -> str:
    if not categories:
        return "Other"
    std = [_standardize_category(c) for c in categories]
    return Counter(std).most_common(1)[0][0]


def _financial_commitment_hint(description: str) -> bool:
    text = description or ""
    if _COMMITMENT_HINT_SUB.search(text):
        return True
    if _COMMITMENT_HINT_BILL.search(text):
        return True
    if _LOAN_WORD.search(text):
        return True
    return False


def _commitment_kind_from_category_and_text(mode_category: str, raw_description: str) -> Optional[str]:
    """Classify using standardized category + generic narration cues from the statement only."""
    std = _standardize_category(mode_category)
    text = raw_description or ""

    if _COMMITMENT_HINT_SUB.search(text):
        return "subscription"
    if std == "Entertainment":
        return "subscription"
    if std in ("Utilities", "Bills"):
        return "bill"
    if std in ("Food", "Transport", "Shopping"):
        return None
    if std in ("Transfers", "Other"):
        return "bill" if _financial_commitment_hint(text) else None
    return None


def _month_tuple(value: datetime.datetime) -> Tuple[int, int]:
    return (value.year, value.month)


def _window_months(anchor: Tuple[int, int], count: int = 6) -> set:
    """Return the `count` most recent (year, month) tuples ending at anchor."""
    year, month = anchor
    months = set()
    for _ in range(count):
        months.add((year, month))
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    return months


def _refresh_detected_commitments(db: Session, user: User) -> None:
    """Rebuild Bill/Subscription rows from transaction history.

    Rules:
      - Group debits by (recurrence_group_key, year, month). Keys are derived
        from cleaned narration (stopwords, sorted tokens) so similar labels
        from the same merchant merge without a merchant whitelist.
      - Representative amount per bucket = max(abs(amount)) to avoid
        double-counting split or partial payments.
      - Recurring: the group must appear in >=3 distinct calendar months
        within the rolling last 6 months (anchored at the canonical month =
        max(transaction date)).
      - Subscription vs bill: standardized transaction category + generic
        narration hints (EMI, rent, subscription, electricity, …) from the
        statement — not hardcoded merchant names.
      - Due / next-billing dates are anchored to the latest debit in-window
        so calendar and bills month filters match the statement month.
      - Emit one Bill OR one Subscription per qualifying group. Calendar
        reads bills, subs, and explicit events directly.
    """
    db.query(Subscription).filter(Subscription.user_id == user.id).delete()
    db.query(Bill).filter(Bill.user_id == user.id).delete()
    db.commit()

    transactions = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id, Transaction.type == "debit")
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    if not transactions:
        return

    canonical = canonical_year_month(transactions)
    if canonical is None:
        today = datetime.datetime.utcnow()
        canonical = (today.year, today.month)
    window = _window_months(canonical, count=6)

    buckets: Dict[Tuple[str, int, int], float] = {}
    latest_in_bucket: Dict[Tuple[str, int, int], Transaction] = {}
    categories_by_group: Dict[str, List[str]] = defaultdict(list)

    for tx in transactions:
        if not tx.date:
            continue
        group_key = _recurrence_group_key(tx.description or "")
        if not group_key:
            continue
        ym = _month_tuple(tx.date)
        if ym in window:
            categories_by_group[group_key].append(tx.category or "Other")
        month_key = ym
        bucket_key = (group_key, *month_key)
        amount = abs(float(tx.amount or 0.0))
        if amount > buckets.get(bucket_key, 0.0):
            buckets[bucket_key] = amount
        current_latest = latest_in_bucket.get(bucket_key)
        if current_latest is None or tx.date > current_latest.date:
            latest_in_bucket[bucket_key] = tx

    months_in_window_by_group: Dict[str, set] = {}
    for (group_key, year, month) in buckets.keys():
        if (year, month) not in window:
            continue
        months_in_window_by_group.setdefault(group_key, set()).add((year, month))

    today = datetime.datetime.utcnow()
    bills_created = 0
    subs_created = 0
    for group_key, months_seen in months_in_window_by_group.items():
        if len(months_seen) < 3:
            continue
        mode_cat = _mode_category(categories_by_group.get(group_key, []))

        candidate_buckets = [
            (k, v) for k, v in buckets.items() if k[0] == group_key and (k[1], k[2]) in window
        ]
        if not candidate_buckets:
            continue
        latest_bucket_key = max(candidate_buckets, key=lambda item: (item[0][1], item[0][2]))[0]
        amount = round(buckets[latest_bucket_key], 2)
        latest_tx = latest_in_bucket[latest_bucket_key]
        title = (latest_tx.description or group_key or "Payment").strip()[:255]

        commitment_type = _commitment_kind_from_category_and_text(mode_cat, latest_tx.description or "")
        if not commitment_type:
            continue

        # Anchor to last debit in-window so dashboard/bills/calendar month views
        # align with the statement (avoid +5d / +30d slipping into next month).
        anchor = latest_tx.date

        if commitment_type == "subscription":
            db.add(
                Subscription(
                    user_id=user.id,
                    name=title,
                    amount=amount,
                    billing_cycle="monthly",
                    status="active",
                    next_billing_date=anchor,
                )
            )
            subs_created += 1
        else:
            status = "paid" if anchor.date() < today.date() else "pending"
            db.add(
                Bill(
                    user_id=user.id,
                    name=title,
                    amount=amount,
                    due_date=anchor,
                    status=status,
                )
            )
            bills_created += 1
    db.commit()
    logger.info(
        "[Commitments] user_id=%s groups_in_window=%s bills=%s subscriptions=%s",
        user.id,
        len(months_in_window_by_group),
        bills_created,
        subs_created,
    )


# ─────────────────────────────────────────────
# SUMMARY COMPUTATION
# ─────────────────────────────────────────────
def _build_summary(db: Session, user, raw_txs: List[Dict]) -> None:
    """Recompute and save UserFinancialSummary using the canonical engine.

    raw_txs is accepted for backwards compatibility but ignored — we always
    read the authoritative transaction set from the database so dashboard,
    chat, and insights share the same numbers.
    """
    del raw_txs  # computed from DB to stay consistent across surfaces

    all_txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    snapshot = compute_snapshot_from_transactions(all_txs)

    cat_dist: Dict[str, float] = {}
    for tx in all_txs:
        if (tx.type or "").lower() != "debit":
            continue
        category = _standardize_category(tx.category or "Other")
        cat_dist[category] = cat_dist.get(category, 0.0) + float(tx.amount or 0.0)

    emi_total = sum(
        float(tx.amount or 0.0)
        for tx in all_txs
        if (tx.category or "") == "EMI / Loans"
        or any(keyword in (tx.description or "").lower() for keyword in ("emi", "loan"))
    )

    user.monthly_income = snapshot.salary

    summary = db.query(UserFinancialSummary).filter_by(user_id=user.id).first()
    if not summary:
        summary = UserFinancialSummary(user_id=user.id)
        db.add(summary)

    summary.total_balance         = snapshot.total_balance
    summary.monthly_income        = snapshot.salary
    summary.monthly_spend         = snapshot.expenses
    summary.emi_total             = emi_total
    summary.savings               = snapshot.savings
    summary.income_detected       = snapshot.salary
    summary.category_distribution = json.dumps(cat_dist)
    summary.last_upload_date      = datetime.datetime.utcnow()
    summary.last_updated          = datetime.datetime.utcnow()
    db.commit()

    _refresh_detected_commitments(db, user)
    upsert_user_insights(db, user, limit=6)



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
    # Always run text-based extraction so partial table matches don't silently
    # drop rows like Swiggy/Amazon that live in narration-only lines.
    _update(45, "Stage 2: Regex heuristic extraction...")
    stage2_txs = _extract_from_text(text)
    logger.info(f"[Pipeline] Stage 2 result: {len(stage2_txs)} transactions")

    combined = _dedupe_raw_transactions(stage1_txs + stage2_txs)
    logger.info(
        f"[Pipeline] Merged stage1+stage2 after dedupe: {len(combined)} transactions"
    )
    fallback_triggered = False

    # ── Stage 4: LLM Fallback Extraction ─────
    if len(combined) == 0:
        _update(55, "Stage 4: LLM fallback extraction (structured parsing found 0 results)...")
        fallback_triggered = True
        combined = _llm_extract_fallback(text)
        logger.info(f"[Pipeline] Stage 4 result: {len(combined)} transactions")

    # ── Stage 3: Hybrid Categorization ───────
    if combined:
        _update(65, "Stage 3: Categorizing transactions...")
        combined = _llm_categorize(combined)

    _update(75, "Deduplicating and saving...")

    # Delete-after-validated-parse: only wipe prior financial data once we
    # know extraction produced something. A bad/empty file never wipes the
    # user's account. _save_transactions stays idempotent via tx_hash.
    if combined:
        delete_user_financial_data(db, user.id)

    # Seed demo cards BEFORE saving so each debit gets a card_id assigned.
    existing_cards = db.query(Card).filter(Card.user_id == user.id).count()
    if existing_cards == 0:
        from services.canonical_cards import create_canonical_cards_for_user

        create_canonical_cards_for_user(db, user)
        db.commit()

    # ── Save to DB ───────────────────────────
    new_saved, valid_extracted = _save_transactions(db, user.id, combined)
    _backfill_card_assignments(db, user.id)
    total_raw   = len(combined)
    confidence  = valid_extracted / total_raw if total_raw > 0 else 0.0

    logger.info(
        f"[Pipeline] Done — raw={total_raw} valid={valid_extracted} new_saved={new_saved} "
        f"confidence={confidence:.2f} fallback={fallback_triggered}"
    )

    _update(90, "Computing financial summary and insights...")

    # ── Final Outcome ─────────────────────────
    if valid_extracted == 0:
        status.status        = "failed"
        status.error_message = "No financial data detected in file. Please upload a valid bank statement."
        db.commit()
        logger.warning(f"[Pipeline] No transactions extracted from '{filename}'")
        return

    # Single summary rebuild from the authoritative DB transactions (not the
    # raw in-memory batch) so bills/subs and snapshot numbers always agree.
    _build_summary(db, user, [])

    # Vectorize the user's transactions and derived insights so the chat
    # agents can retrieve user-scoped semantic context. Failures here must
    # not fail activation — the chat path still works from the DB snapshot.
    try:
        rag_counts = vectorize_financial_rag(combined, filename, user_id=user.id)
        logger.info(
            "[Pipeline] Vectorized RAG — transactions=%s insights=%s",
            rag_counts.get("transactions", 0),
            rag_counts.get("insights", 0),
        )
    except Exception as exc:
        logger.warning("[Pipeline] RAG vectorization failed (non-fatal): %s", exc)

    tx_count = db.query(Transaction).filter(Transaction.user_id == user.id).count()
    bill_count = db.query(Bill).filter(Bill.user_id == user.id).count()
    sub_count = db.query(Subscription).filter(Subscription.user_id == user.id).count()
    event_count = db.query(CalendarEvent).filter(CalendarEvent.user_id == user.id).count()
    logger.info(
        "[Pipeline] Summary rebuilt — transactions=%s bills=%s subscriptions=%s events=%s",
        tx_count, bill_count, sub_count, event_count,
    )

    if not user.credit_score:
        user.credit_score = 742
        db.commit()

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

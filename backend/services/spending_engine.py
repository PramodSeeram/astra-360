"""Deterministic spending math from transactions (Phase 1: data-first path).

No LLM. All totals and breakdowns are computed in Python.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from models import Transaction

from services.financial_engine import canonical_year_month, transactions_in_month

_MONTH_NAMES: Dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


def filter_transactions_by_month(
    transactions: Iterable[Transaction], month: int, year: int
) -> List[Transaction]:
    return transactions_in_month(transactions, year, month)


def normalize_merchant(description: Optional[str]) -> str:
    raw = (description or "").strip().lower().split("\n")[0].strip()
    raw = re.sub(r"\s+", " ", raw)
    if not raw:
        return "unknown"
    if "swiggy" in raw:
        return "swiggy"
    if "zomato" in raw:
        return "zomato"
    if "netflix" in raw:
        return "netflix"
    if "uber" in raw:
        return "uber"
    if "amazon" in raw or "amzn" in raw:
        return "amazon"
    token = re.sub(r"^[^a-z0-9]+", "", raw)
    token = re.split(r"[\s/|-]+", token)[0] if token else ""
    token = re.sub(r"[^a-z0-9]", "", token)
    return token[:40] if token else "unknown"


def _shift_month(year: int, month: int, delta: int) -> Tuple[int, int]:
    m = month + delta
    y = year
    while m > 12:
        m -= 12
        y += 1
    while m < 1:
        m += 12
        y -= 1
    return y, m


def parse_query_month_window(
    message: str, transactions: List[Transaction]
) -> List[Tuple[int, int]]:
    """Resolve (year, month) windows from natural language.

    If no month is mentioned, uses latest month in data (canonical_year_month).
    """
    msg = (message or "").lower()
    cy = canonical_year_month(transactions)
    if not cy:
        return []

    y, m = cy

    # Explicit comparison: "feb and march", "feb vs march", "february vs march"
    vs_parts = re.split(r"\bvs\.?\b|\band\b|,", msg)
    found_months: List[int] = []
    for token in vs_parts:
        for name, num in _MONTH_NAMES.items():
            if re.search(rf"\b{re.escape(name)}\b", token):
                found_months.append(num)
                break
    found_months = list(dict.fromkeys(found_months))
    if len(found_months) >= 2:
        m1, m2 = sorted(found_months[:2])
        return [(y, m1), (y, m2)]

    if "last month" in msg:
        return [_shift_month(y, m, -1)]

    if "this month" in msg:
        return [(y, m)]

    for name, num in _MONTH_NAMES.items():
        if re.search(rf"\b{re.escape(name)}\b", msg):
            yy = y
            if num > m and "last" not in msg and "prev" not in msg:
                yy = y - 1
            return [(yy, num)]

    return [(y, m)]


def compute_spending(
    transactions: List[Transaction],
    windows: Optional[List[Tuple[int, int]]] = None,
) -> Dict[str, Any]:
    """Aggregate debits by month, category, and normalized merchant.

    Returns monthly buckets plus top-level swiggy_total / zomato_total
    across all selected windows.
    """
    if windows is None:
        cy = canonical_year_month(transactions)
        windows = [cy] if cy else []

    monthly: Dict[str, Any] = {}
    category: Dict[str, float] = defaultdict(float)
    merchant: Dict[str, float] = defaultdict(float)
    swiggy_total = 0.0
    zomato_total = 0.0

    for year, month in windows:
        key = f"{year:04d}-{month:02d}"
        month_txs = transactions_in_month(transactions, year, month)
        debits = [tx for tx in month_txs if (tx.type or "").lower() == "debit"]
        by_cat: Dict[str, float] = defaultdict(float)
        by_merch: Dict[str, float] = defaultdict(float)
        m_swiggy = 0.0
        m_zomato = 0.0
        for tx in debits:
            amt = abs(float(tx.amount or 0.0))
            desc_l = (tx.description or "").lower()
            cat = (tx.category or "Other").strip() or "Other"
            by_cat[cat] += amt
            category[cat] += amt
            mk = normalize_merchant(tx.description)
            by_merch[mk] += amt
            merchant[mk] += amt
            if "swiggy" in desc_l:
                m_swiggy += amt
                swiggy_total += amt
            if "zomato" in desc_l:
                m_zomato += amt
                zomato_total += amt
        monthly[key] = {
            "total_debit": round(sum(by_cat.values()), 2),
            "by_category": {k: round(v, 2) for k, v in sorted(by_cat.items())},
            "by_merchant": {k: round(v, 2) for k, v in sorted(by_merch.items())},
            "swiggy_total": round(m_swiggy, 2),
            "zomato_total": round(m_zomato, 2),
        }

    return {
        "monthly": monthly,
        "category": {k: round(v, 2) for k, v in sorted(category.items())},
        "merchant": {k: round(v, 2) for k, v in sorted(merchant.items())},
        "swiggy_total": round(swiggy_total, 2),
        "zomato_total": round(zomato_total, 2),
        "windows": [f"{yy:04d}-{mm:02d}" for yy, mm in windows],
    }

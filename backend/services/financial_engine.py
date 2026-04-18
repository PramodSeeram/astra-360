"""Canonical financial math for Astra 360.

All dashboard and chat surfaces read from the same snapshot so salary,
expenses, savings, and total balance never drift across views. No LLM is
used for these numbers — they are computed deterministically from the DB.

`canonical_year_month` is the single source of truth for "current month":
every caller (engine, dashboard, cards, insights, chat) must derive the
headline month via this helper so we never disagree on which month we are
summarizing.
"""

import datetime as dt
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from models import Transaction, User


SALARY_KEYWORDS: Tuple[str, ...] = (
    "salary",
    "sal",
    "payroll",
    "infy",
    "wipro",
    "tcs",
)

SUBSCRIPTION_KEYWORDS: Tuple[str, ...] = (
    "netflix",
    "spotify",
    "prime",
    "amazon prime",
    "hotstar",
    "zee5",
    "sony liv",
    "youtube",
    "subscription",
    "ott",
)

RENT_KEYWORDS: Tuple[str, ...] = ("rent", "landlord", "housing")

# Narration-based (do not trust LLM category). Word-boundary on EMI avoids "premium".
_RENT_IN_DESC = re.compile(r"\brent\b|/rent/", re.IGNORECASE)
_EMI_IN_DESC = re.compile(r"\bemi\b|\bnach\b", re.IGNORECASE)


@dataclass
class FinancialSnapshot:
    salary: float
    expenses: float
    savings: float
    total_balance: float
    top_category: Optional[str]
    top_category_amount: float
    subscriptions_total: float
    monthly_breakdown: List[Dict]
    transactions_found: bool
    headline_month: Optional[str] = None
    current_year: Optional[int] = None
    current_month: Optional[int] = None
    salary_months_used: List[str] = field(default_factory=list)
    top_categories: List[Tuple[str, float]] = field(default_factory=list)
    subscriptions_items: List[Dict[str, float | str]] = field(default_factory=list)
    rent_total: float = 0.0
    emi_total: float = 0.0
    top_debits: List[Dict[str, float | str]] = field(default_factory=list)


def _month_key(value: dt.datetime) -> str:
    return value.strftime("%Y-%m")


def canonical_year_month(transactions: Iterable[Transaction]) -> Optional[Tuple[int, int]]:
    """Return (year, month) derived from max(tx.date); None if no dated txs.

    This is the ONLY sanctioned definition of "current month". Callers in
    other services must import and use this helper to stay consistent with
    the snapshot — do not recompute ad-hoc.
    """
    dated = [tx.date for tx in transactions if getattr(tx, "date", None)]
    if not dated:
        return None
    ref = max(dated)
    return ref.year, ref.month


def transactions_in_month(
    transactions: Iterable[Transaction], year: int, month: int
) -> List[Transaction]:
    return [
        tx for tx in transactions
        if tx.date and tx.date.year == year and tx.date.month == month
    ]


def _description_has_salary_keyword(description: Optional[str]) -> bool:
    desc = (description or "").lower()
    if not desc:
        return False
    tokens = set(filter(None, (t.strip() for t in desc.replace("/", " ").replace("-", " ").split())))
    for keyword in SALARY_KEYWORDS:
        # "sal" is short — require token match so "casual"/"sale" don't count.
        if keyword == "sal":
            if "sal" in tokens:
                return True
            continue
        if keyword in desc:
            return True
    return False


def _salary_per_month(transactions: Iterable[Transaction]) -> Dict[str, float]:
    """Pick one salary amount per month.

    Rule (per spec):
      - Among credits in the month, prefer the largest credit whose
        description contains a salary keyword.
      - If no credit matches a keyword, fallback to the largest credit in
        that month.
    """
    credits_by_month: Dict[str, List[Transaction]] = defaultdict(list)
    for tx in transactions:
        if (tx.type or "").lower() != "credit" or not tx.date:
            continue
        credits_by_month[_month_key(tx.date)].append(tx)

    per_month: Dict[str, float] = {}
    for month_key, credits in credits_by_month.items():
        keyword_hits = [tx for tx in credits if _description_has_salary_keyword(tx.description)]
        pool = keyword_hits or credits
        best = max(pool, key=lambda tx: float(tx.amount or 0.0))
        per_month[month_key] = float(best.amount or 0.0)
    return per_month


def _latest_three_month_average(per_month: Dict[str, float]) -> Tuple[float, List[str]]:
    if not per_month:
        return 0.0, []
    latest_keys = sorted(per_month.keys(), reverse=True)[:3]
    amounts = [per_month[key] for key in latest_keys]
    return round(sum(amounts) / len(amounts), 2), sorted(latest_keys)


def _total_balance(transactions: List[Transaction]) -> float:
    """Balance from latest tx's statement_balance, else running sum.

    Guard: if the parsed statement_balance is negative or non-numeric we
    treat it as unreliable (bad OCR / sign flip) and fall back to running
    balance so demos never show nonsense.
    """
    dated = [tx for tx in transactions if tx.date]
    if not dated:
        return 0.0
    latest = max(dated, key=lambda tx: (tx.date, tx.id))
    raw = getattr(latest, "statement_balance", None)
    if raw is not None:
        try:
            value = float(raw)
            if value >= 0:
                return round(value, 2)
        except (TypeError, ValueError):
            pass
    return _running_balance(transactions)


def _running_balance(transactions: List[Transaction]) -> float:
    ordered = sorted(
        [tx for tx in transactions if tx.date],
        key=lambda tx: (tx.date, tx.id),
    )
    balance = 0.0
    for tx in ordered:
        amount = float(tx.amount or 0.0)
        if (tx.type or "").lower() == "credit":
            balance += amount
        else:
            balance -= amount
    return round(balance, 2)


def _top_category_in_month(
    transactions: Iterable[Transaction], year: int, month: int
) -> Tuple[Optional[str], float]:
    totals: Dict[str, float] = defaultdict(float)
    for tx in transactions:
        if (tx.type or "").lower() != "debit" or not tx.date:
            continue
        if tx.date.year != year or tx.date.month != month:
            continue
        key = (tx.category or "Other").strip() or "Other"
        totals[key] += abs(float(tx.amount or 0.0))
    if not totals:
        return None, 0.0
    name, amount = max(totals.items(), key=lambda item: item[1])
    return name, round(amount, 2)


def _category_distribution_in_month(
    transactions: Iterable[Transaction], year: int, month: int
) -> Dict[str, float]:
    totals: Dict[str, float] = defaultdict(float)
    for tx in transactions:
        if (tx.type or "").lower() != "debit" or not tx.date:
            continue
        if tx.date.year != year or tx.date.month != month:
            continue
        key = (tx.category or "Other").strip() or "Other"
        totals[key] += abs(float(tx.amount or 0.0))
    return {k: round(v, 2) for k, v in totals.items()}


def _subscriptions_total(transactions: Iterable[Transaction]) -> float:
    """Estimate monthly subscription spend from recurring entertainment debits."""
    counts: Dict[str, float] = defaultdict(float)
    frequency: Dict[str, int] = defaultdict(int)
    for tx in transactions:
        if (tx.type or "").lower() != "debit":
            continue
        key = (tx.description or "").strip().lower()
        if not key:
            continue
        frequency[key] += 1
        counts[key] = abs(float(tx.amount or 0.0))
    recurring_amounts = [amount for key, amount in counts.items() if frequency[key] >= 3]
    return round(sum(recurring_amounts), 2)


def _contains_keyword(text: Optional[str], keywords: Tuple[str, ...]) -> bool:
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    return any(keyword in lowered for keyword in keywords)


def _top_categories_in_month(
    transactions: Iterable[Transaction], year: Optional[int], month: Optional[int], limit: int = 3
) -> List[Tuple[str, float]]:
    if year is None or month is None:
        return []
    distribution = _category_distribution_in_month(transactions, year, month)
    ordered = sorted(distribution.items(), key=lambda item: item[1], reverse=True)
    return [(name, round(amount, 2)) for name, amount in ordered[:limit] if amount > 0]


def _subscription_items_in_month(
    transactions: Iterable[Transaction], year: Optional[int], month: Optional[int]
) -> List[Dict[str, float | str]]:
    if year is None or month is None:
        return []

    totals: Dict[str, float] = defaultdict(float)
    for tx in transactions:
        if (tx.type or "").lower() != "debit" or not tx.date:
            continue
        if tx.date.year != year or tx.date.month != month:
            continue
        description = (tx.description or "").strip()
        category = (tx.category or "").strip().lower()
        if _contains_keyword(description, SUBSCRIPTION_KEYWORDS) or category == "entertainment":
            key = description or "Subscription"
            totals[key] += abs(float(tx.amount or 0.0))

    ordered = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return [
        {"name": name, "amount": round(amount, 2)}
        for name, amount in ordered
        if amount > 0
    ]


def _rent_total_in_month(transactions: Iterable[Transaction], year: Optional[int], month: Optional[int]) -> float:
    if year is None or month is None:
        return 0.0

    total = 0.0
    for tx in transactions:
        if (tx.type or "").lower() != "debit" or not tx.date:
            continue
        if tx.date.year != year or tx.date.month != month:
            continue
        description = tx.description or ""
        category = (tx.category or "").lower()
        if _RENT_IN_DESC.search(description) or _contains_keyword(description, RENT_KEYWORDS) or "rent" in category:
            total += abs(float(tx.amount or 0.0))
    return round(total, 2)


def _emi_total_in_month(transactions: Iterable[Transaction], year: Optional[int], month: Optional[int]) -> float:
    if year is None or month is None:
        return 0.0
    total = 0.0
    for tx in transactions:
        if (tx.type or "").lower() != "debit" or not tx.date:
            continue
        if tx.date.year != year or tx.date.month != month:
            continue
        description = tx.description or ""
        if _EMI_IN_DESC.search(description):
            total += abs(float(tx.amount or 0.0))
    return round(total, 2)


def _top_debits_in_month(
    transactions: Iterable[Transaction], year: Optional[int], month: Optional[int], limit: int = 3
) -> List[Dict[str, float | str]]:
    if year is None or month is None:
        return []

    items: List[Tuple[str, float]] = []
    for tx in transactions:
        if (tx.type or "").lower() != "debit" or not tx.date:
            continue
        if tx.date.year != year or tx.date.month != month:
            continue
        amount = abs(float(tx.amount or 0.0))
        if amount <= 0:
            continue
        items.append(((tx.description or "Debit transaction").strip(), amount))

    ordered = sorted(items, key=lambda item: item[1], reverse=True)[:limit]
    return [{"name": name, "amount": round(amount, 2)} for name, amount in ordered]


def build_financial_snapshot(db: Session, user: User) -> FinancialSnapshot:
    transactions: List[Transaction] = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    return compute_snapshot_from_transactions(transactions)


def compute_snapshot_from_transactions(transactions: List[Transaction]) -> FinancialSnapshot:
    if not transactions:
        return FinancialSnapshot(
            salary=0.0,
            expenses=0.0,
            savings=0.0,
            total_balance=0.0,
            top_category=None,
            top_category_amount=0.0,
            subscriptions_total=0.0,
            monthly_breakdown=[],
            transactions_found=False,
        )

    canonical = canonical_year_month(transactions)
    current_year, current_month = canonical if canonical else (None, None)

    salary_per_month = _salary_per_month(transactions)
    salary, salary_months = _latest_three_month_average(salary_per_month)

    expenses = 0.0
    if canonical is not None:
        expenses = round(
            sum(
                abs(float(tx.amount or 0.0))
                for tx in transactions_in_month(transactions, current_year, current_month)
                if (tx.type or "").lower() == "debit"
            ),
            2,
        )
    savings = round(salary - expenses, 2)

    debit_totals: Dict[str, float] = defaultdict(float)
    for tx in transactions:
        if (tx.type or "").lower() != "debit" or not tx.date:
            continue
        debit_totals[_month_key(tx.date)] += abs(float(tx.amount or 0.0))
    all_months = sorted({_month_key(tx.date) for tx in transactions if tx.date})
    monthly_breakdown = [
        {
            "month": month,
            "salary": round(salary_per_month.get(month, 0.0), 2),
            "expenses": round(debit_totals.get(month, 0.0), 2),
            "savings": round(salary_per_month.get(month, 0.0) - debit_totals.get(month, 0.0), 2),
        }
        for month in all_months
    ]

    total_balance = _total_balance(transactions)

    top_category_name, top_category_amount = (None, 0.0)
    if canonical is not None:
        top_category_name, top_category_amount = _top_category_in_month(
            transactions, current_year, current_month
        )
    subs_total = _subscriptions_total(transactions)
    top_categories = _top_categories_in_month(transactions, current_year, current_month, limit=5)
    subscription_items = _subscription_items_in_month(transactions, current_year, current_month)
    rent_total = _rent_total_in_month(transactions, current_year, current_month)
    emi_total = _emi_total_in_month(transactions, current_year, current_month)
    top_debits = _top_debits_in_month(transactions, current_year, current_month, limit=3)

    headline_month = (
        dt.date(current_year, current_month, 1).strftime("%Y-%m")
        if canonical is not None
        else None
    )

    return FinancialSnapshot(
        salary=salary,
        expenses=expenses,
        savings=savings,
        total_balance=total_balance,
        top_category=top_category_name,
        top_category_amount=top_category_amount,
        subscriptions_total=subs_total,
        monthly_breakdown=monthly_breakdown,
        transactions_found=True,
        headline_month=headline_month,
        current_year=current_year,
        current_month=current_month,
        salary_months_used=salary_months,
        top_categories=top_categories,
        subscriptions_items=subscription_items,
        rent_total=rent_total,
        emi_total=emi_total,
        top_debits=top_debits,
    )


def snapshot_category_distribution(
    transactions: Iterable[Transaction], snapshot: FinancialSnapshot
) -> Dict[str, float]:
    """Category totals for the snapshot's canonical month only."""
    if snapshot.current_year is None or snapshot.current_month is None:
        return {}
    return _category_distribution_in_month(
        transactions, snapshot.current_year, snapshot.current_month
    )


def _format_inr(amount: float) -> str:
    return f"₹{amount:,.0f}"


def _format_pct(value: float) -> str:
    return f"{value:.1f}%"


def _format_month_label(snapshot: "FinancialSnapshot") -> str:
    """Human-friendly label for the canonical snapshot month."""
    if snapshot.current_year is None or snapshot.current_month is None:
        return "latest statement"
    try:
        return dt.date(snapshot.current_year, snapshot.current_month, 1).strftime("%b %Y")
    except Exception:
        return snapshot.headline_month or "latest statement"


def _freshness_footer(snapshot: "FinancialSnapshot") -> str:
    """Short, single-line freshness annotation appended to finance replies."""
    month_label = _format_month_label(snapshot)
    tx_count = len(snapshot.monthly_breakdown)
    if tx_count:
        return f"_Basis: {month_label} snapshot · {tx_count} month(s) of bank data._"
    return f"_Basis: {month_label} snapshot._"


def _classify_finance_intent(query: str) -> str:
    text = (query or "").lower()
    if any(
        word in text
        for word in ("salary", "income", "payroll", "how much do i earn", "monthly pay")
    ):
        return "salary"
    if any(word in text for word in ("subscription", "subscribe", "ott", "netflix", "spotify", "recurring")):
        return "subscriptions"
    if any(word in text for word in ("emi", "loan installment", "installment", "nach")):
        return "emi"
    if any(word in text for word in ("rent", "housing", "landlord")):
        return "rent"
    if any(word in text for word in ("biggest", "top", "most", "highest", "largest")):
        return "top_spend"
    if any(word in text for word in ("unusual", "strange", "weird", "suspicious", "anomaly")):
        return "top_debits"
    return "summary"


def _render_subscriptions(snapshot: FinancialSnapshot) -> str:
    month_label = _format_month_label(snapshot)
    if snapshot.subscriptions_total <= 0:
        return f"No recurring subscriptions detected for {month_label}."
    lines = [
        f"**Subscriptions · {month_label}**",
        f"Monthly run-rate: {_format_inr(snapshot.subscriptions_total)}",
        "",
    ]
    for item in snapshot.subscriptions_items[:3]:
        lines.append(f"• {item['name']} — {_format_inr(float(item['amount']))}")
    return "\n".join(lines)


def _render_rent(snapshot: FinancialSnapshot) -> str:
    month_label = _format_month_label(snapshot)
    if snapshot.rent_total <= 0:
        return f"No rent payments detected for {month_label}."
    return (
        f"**Rent · {month_label}**\n"
        f"You paid approximately {_format_inr(snapshot.rent_total)} in rent "
        f"(matched from your transaction descriptions)."
    )


def _render_salary(snapshot: FinancialSnapshot) -> str:
    if snapshot.salary <= 0:
        return "No salary credits detected in your recent statements."
    months = snapshot.salary_months_used or []
    basis = (
        f" (average of {', '.join(months)})"
        if months
        else " (3-month average of salary credits)"
    )
    return (
        f"**Salary**\n"
        f"Your monthly salary is approximately {_format_inr(snapshot.salary)}{basis}."
    )


def _render_emi(snapshot: FinancialSnapshot) -> str:
    month_label = _format_month_label(snapshot)
    if snapshot.emi_total <= 0:
        return f"No EMI / NACH debit lines detected for {month_label}."
    return (
        f"**EMI & NACH · {month_label}**\n"
        f"EMI-related debits total about {_format_inr(snapshot.emi_total)} "
        f"(matched via EMI/NACH keywords)."
    )


def _render_top_spend(snapshot: FinancialSnapshot) -> str:
    month_label = _format_month_label(snapshot)
    if not snapshot.top_categories:
        return f"No category spend data found for {month_label}."
    lines = [f"**Top spend · {month_label}**"]
    for name, amount in snapshot.top_categories[:3]:
        lines.append(f"• {name} — {_format_inr(amount)}")
    return "\n".join(lines)


def _render_top_debits(snapshot: FinancialSnapshot) -> str:
    month_label = _format_month_label(snapshot)
    if not snapshot.top_debits:
        return f"No large debit transactions found for {month_label}."
    lines = [f"**Largest debits · {month_label}**"]
    for item in snapshot.top_debits[:3]:
        lines.append(f"• {item['name']} — {_format_inr(float(item['amount']))}")
    return "\n".join(lines)


def _render_summary(snapshot: FinancialSnapshot) -> str:
    if not snapshot.transactions_found:
        return "Please upload your bank statement to generate insights."

    month_label = _format_month_label(snapshot)
    lines = [
        f"**Snapshot · {month_label}**",
        f"• Salary: {_format_inr(snapshot.salary)}",
        f"• Expenses: {_format_inr(snapshot.expenses)}",
        f"• Savings: {_format_inr(snapshot.savings)}",
        f"• Total balance: {_format_inr(snapshot.total_balance)}",
        "",
        "**Insights**",
    ]
    insights: List[str] = []

    if snapshot.salary > 0:
        rate = (snapshot.savings / snapshot.salary) * 100
        if snapshot.savings < 0:
            insights.append(
                f"• You spent {_format_pct(abs(rate))} more than you earned — "
                "review discretionary categories first."
            )
        else:
            insights.append(
                f"• You saved about {_format_pct(rate)} of your salary."
            )

    if snapshot.top_category:
        insights.append(
            f"• Top category: {snapshot.top_category} at "
            f"{_format_inr(snapshot.top_category_amount)}."
        )

    if snapshot.rent_total > 0:
        insights.append(f"• Rent: {_format_inr(snapshot.rent_total)}.")
    if snapshot.emi_total > 0:
        insights.append(f"• EMI / NACH: {_format_inr(snapshot.emi_total)}.")
    if snapshot.subscriptions_total > 0:
        insights.append(
            f"• Subscriptions run-rate: {_format_inr(snapshot.subscriptions_total)}/month."
        )

    if not insights:
        insights.append("• Nothing unusual detected this month.")

    lines.extend(insights[:4])
    return "\n".join(lines)


def render_finance_answer(query: str, snapshot: FinancialSnapshot) -> str:
    """Produce a human-readable finance response — never raw JSON.

    Every reply is anchored to the canonical snapshot month and suffixed
    with a freshness line so users can tell the answer is recomputed live
    from their latest statement (not a cached blurb).
    """

    if not snapshot.transactions_found:
        return "Please upload your bank statement to generate insights."

    intent = _classify_finance_intent(query)
    renderer = {
        "salary": _render_salary,
        "subscriptions": _render_subscriptions,
        "emi": _render_emi,
        "rent": _render_rent,
        "top_spend": _render_top_spend,
        "top_debits": _render_top_debits,
    }.get(intent, _render_summary)

    body = renderer(snapshot)
    return f"{body}\n\n{_freshness_footer(snapshot)}"

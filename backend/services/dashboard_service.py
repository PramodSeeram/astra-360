"""
Dashboard Service Layer — Astra 360
Maps DB models to structured JSON for dashboard screens.
PARTIAL state now surfaces real data with an informational banner.
"""

import calendar
import json
import time
import datetime
from collections import defaultdict
from sqlalchemy import extract
from sqlalchemy.orm import Session
from models import Bill, Card, CreditAccount, Loan, Subscription, Transaction, User, UserFinancialSummary, UserProcessingStatus, get_user_by_external_id
from services.user_state import get_user_state


def _timestamp_to_iso(ts):
    """Convert unix timestamp or datetime to ISO string."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))
    return ts.strftime("%Y-%m-%dT%H:%M:%S")


def _format_inr(amount: float) -> str:
    return f"₹{amount:,.0f}"


def _bill_category(name: str) -> str:
    text = (name or "").lower()
    if any(term in text for term in ("netflix", "spotify", "prime", "hotstar", "youtube", "subscription", "ott")):
        return "Entertainment"
    if any(term in text for term in ("electricity", "water", "gas", "internet", "mobile", "wifi", "broadband")):
        return "Utilities"
    if "rent" in text:
        return "Rent"
    if any(term in text for term in ("emi", "loan")):
        return "EMI"
    if "card" in text and "bill" in text:
        return "Credit Card"
    return "Bills"


def _bill_provider(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return "Auto-detected"
    return text.replace(" Bill", "").replace(" bill", "").strip()


def _status_for_due_date(due_date: datetime.datetime, status: str) -> str:
    if (status or "").lower() == "paid":
        return "Paid"
    days_until_due = (due_date.date() - datetime.datetime.utcnow().date()).days
    if days_until_due <= 7:
        return "due-soon"
    return "upcoming"


def _month_label(year: int, month: int) -> str:
    return f"{calendar.month_name[month]} {year}"


def _normalize_bill_description(description: str) -> str:
    text = (description or "").strip().lower()
    compact = " ".join(text.split())
    replacements = {
        "wifi": "internet",
        "broadband": "internet",
        "postpaid": "mobile",
        "phone": "mobile",
        "elec": "electricity",
    }
    for source, target in replacements.items():
        compact = compact.replace(source, target)

    if "electricity" in compact:
        return "Electricity Bill"
    if "internet" in compact:
        return "Internet Bill"
    if "water" in compact:
        return "Water Bill"
    if "gas" in compact:
        return "Gas Bill"
    if "mobile" in compact:
        return "Mobile Bill"
    if "rent" in compact:
        return "Rent"
    return (description or "Bill").strip().title()


def _month_window(year: int, month: int) -> tuple[datetime.datetime, datetime.datetime]:
    start = datetime.datetime(year, month, 1)
    if month == 12:
        end = datetime.datetime(year + 1, 1, 1)
    else:
        end = datetime.datetime(year, month + 1, 1)
    return start, end


def _default_bills_month(user: User) -> tuple[int, int]:
    dated_transactions = [tx.date for tx in user.transactions if tx.date]
    if dated_transactions:
        latest = max(dated_transactions)
        return latest.year, latest.month
    today = datetime.datetime.utcnow()
    return today.year, today.month


def _average_monthly_bill_amount(
    db: Session,
    user_id: int,
    normalized_name: str,
    month_start: datetime.datetime,
) -> float:
    three_months_ago = month_start - datetime.timedelta(days=92)
    historical_transactions = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user_id,
            Transaction.type == "debit",
            Transaction.category.in_(["Utilities", "Bills"]),
            Transaction.date >= three_months_ago,
            Transaction.date < month_start,
        )
        .order_by(Transaction.date.asc())
        .all()
    )

    monthly_totals: dict[tuple[int, int], float] = defaultdict(float)
    for tx in historical_transactions:
        if _normalize_bill_description(tx.description) != normalized_name:
            continue
        monthly_totals[(tx.date.year, tx.date.month)] += float(tx.amount or 0.0)

    if not monthly_totals:
        return 0.0

    values = list(monthly_totals.values())[-3:]
    return round(sum(values) / len(values), 2)


def _build_salary_reminders(transactions: list[Transaction], year: int, month: int) -> list[dict]:
    salary_txs = [
        tx for tx in transactions
        if (tx.type or "").lower() == "credit"
        and (
            (tx.category or "").lower() == "salary"
            or "salary" in (tx.description or "").lower()
        )
    ]
    if not salary_txs:
        return []

    latest_salary = max(salary_txs, key=lambda tx: tx.date)
    return [{
        "id": 300000 + latest_salary.id,
        "date": latest_salary.date.day,
        "type": "investment",
        "tag": "SALARY",
        "title": "Salary Credit Expected",
        "subtitle": latest_salary.description or "Monthly salary credit",
        "amount": f"+ ₹{latest_salary.amount:,.0f}",
    }]


def _build_emi_reminders(loans: list[Loan]) -> list[dict]:
    reminders = []
    for index, loan in enumerate(loans):
        due_day = min(5 + index * 5, 28)
        reminders.append({
            "id": 200000 + loan.id,
            "date": due_day,
            "type": "bill",
            "tag": "EMI",
            "title": f"{loan.loan_type} EMI",
            "subtitle": "Monthly EMI reminder",
            "amount": f"₹{loan.emi:,.0f}",
        })
    return reminders


def get_transactions_by_month(db: Session, user_id: int, year: int, month: int) -> list[Transaction]:
    return db.query(Transaction).filter(
        Transaction.user_id == user_id,
        extract("year", Transaction.date) == year,
        extract("month", Transaction.date) == month,
    ).order_by(Transaction.date.asc()).all()


# ──────────────────────────────────────────────
# HOME SUMMARY
# ──────────────────────────────────────────────
def get_home_data(db: Session, external_id: str) -> dict | None:
    user = get_user_by_external_id(db, external_id)
    if not user:
        return None

    state   = get_user_state(db, user)
    summary = user.financial_summary
    status  = user.processing_status

    # Balance: use summary if available, else sum cards
    total_balance      = summary.total_balance if summary else sum(c.balance for c in user.cards)
    total_savings      = summary.savings if summary else 0.0
    monthly_spend      = summary.monthly_spend if summary else 0.0
    total_investments  = 0.0
    total_credit_due   = sum(b.amount for b in user.bills if b.status != "paid")
    category_dist      = json.loads(summary.category_distribution) if (summary and summary.category_distribution) else {}

    first_name = user.name.split()[0] if user.name else "User"
    last_name  = user.name.split()[-1] if len(user.name.split()) > 1 else ""
    initials   = (first_name[:1] + last_name[:1]).upper() if last_name else first_name[:2].upper()

    # State-aware config
    has_data  = state in ("ACTIVE", "PARTIAL")
    is_active = state == "ACTIVE"
    is_partial = state == "PARTIAL"

    # Insights — shown for ACTIVE and PARTIAL
    insights = []
    if has_data:
        tx_count = db.query(Transaction).filter(Transaction.user_id == user.id).count()
        if is_active:
            insights.append({"id": 1, "type": "info",    "text": f"Welcome back, {first_name}! Your financial profile is fully activated.", "time": "Now"})
        if is_partial:
            insights.append({"id": 1, "type": "warning", "text": f"Partial data loaded ({tx_count} transactions). Upload more for complete insights.", "time": "Now"})
        if monthly_spend > 0:
            insights.append({"id": 2, "type": "spend",   "text": f"Monthly spend so far: {_format_inr(monthly_spend)}", "time": "This month"})
        if total_credit_due > 0:
            insights.append({"id": 3, "type": "alert",   "text": f"Bills due: {_format_inr(total_credit_due)}", "time": "Upcoming"})
        if category_dist:
            top_cat = max(category_dist, key=category_dist.get)
            insights.append({"id": 4, "type": "info",    "text": f"Top spending category: {top_cat} ({_format_inr(category_dist[top_cat])})", "time": "All time"})

    return {
        "user_id":           external_id,
        "state":             state,
        "activation_required": not is_active,
        "processing_status": {
            "status":   status.status   if status else "idle",
            "progress": status.progress if status else 0,
            "stage":    status.stage    if status else "Waiting for data",
        } if state != "ACTIVE" else None,
        "first_name":        first_name,
        "last_name":         last_name,
        "initials":          initials,
        "balance":           total_balance,
        "savings":           total_savings,
        "monthly_spend":     monthly_spend,
        "investments":       total_investments,
        "credit_due":        total_credit_due,
        "credit_score":      user.credit_score,
        "category_distribution": category_dist,
        "insights":          insights,
        "has_data":          has_data,
        "data_quality_score": summary.data_quality_score if summary else 0.0,
        "source":            "mysql_db",
        "last_updated":      _timestamp_to_iso(datetime.datetime.now()),
        "data_sources":      ["MySQL DB", "Uploaded Statements"] if has_data else ["MySQL DB"],
        "message": (
            None if is_active
            else "Upload more data for better insights." if is_partial
            else "Please upload your bank statement to activate insights."
        ),
    }


# ──────────────────────────────────────────────
# BILLS & SUBSCRIPTIONS
# ──────────────────────────────────────────────
def get_bills_data(
    db: Session,
    external_id: str,
    year: int | None = None,
    month: int | None = None,
) -> dict | None:
    user = get_user_by_external_id(db, external_id)
    if not user:
        return None

    selected_year, selected_month = (year, month) if year and month else _default_bills_month(user)
    month_start, month_end = _month_window(selected_year, selected_month)
    now = datetime.datetime.utcnow()

    txs = (
        db.query(Transaction)
        .filter(
            Transaction.user_id == user.id,
            Transaction.type == "debit",
            Transaction.category.in_(["Utilities", "Bills"]),
            Transaction.date >= month_start,
            Transaction.date < month_end,
        )
        .order_by(Transaction.date.asc())
        .all()
    )

    grouped: dict[str, list[Transaction]] = defaultdict(list)
    for tx in txs:
        grouped[_normalize_bill_description(tx.description)].append(tx)

    explicit_bill_names = {
        _normalize_bill_description(bill.name)
        for bill in user.bills
        if bill.due_date.year == selected_year and bill.due_date.month == selected_month
    }
    bills = []
    for normalized_name, items in sorted(grouped.items()):
        if normalized_name in explicit_bill_names:
            continue
        latest = max(items, key=lambda tx: tx.date)
        avg = _average_monthly_bill_amount(db, user.id, normalized_name, month_start)
        due_date = latest.date + datetime.timedelta(days=30)
        bills.append(
            {
                "name": normalized_name,
                "amount": round(float(latest.amount or 0.0), 2),
                "due_date": due_date.date().isoformat(),
                "avg": avg,
                "status": _status_for_due_date(due_date, "pending"),
                "provider": _bill_provider(normalized_name),
                "category": _bill_category(normalized_name),
            }
        )

    for bill in user.bills:
        if bill.due_date.year != selected_year or bill.due_date.month != selected_month:
            continue
        bills.append(
            {
                "name": bill.name,
                "amount": round(float(bill.amount or 0.0), 2),
                "due_date": bill.due_date.date().isoformat(),
                "avg": _average_monthly_bill_amount(db, user.id, _normalize_bill_description(bill.name), month_start),
                "status": _status_for_due_date(bill.due_date, bill.status),
                "provider": _bill_provider(bill.name),
                "category": _bill_category(bill.name),
            }
        )

    for subscription in user.subscriptions:
        next_billing = subscription.next_billing_date or month_start
        if next_billing.year != selected_year or next_billing.month != selected_month:
            continue
        bills.append(
            {
                "name": subscription.name,
                "amount": round(float(subscription.amount or 0.0), 2),
                "due_date": next_billing.date().isoformat(),
                "avg": round(float(subscription.amount or 0.0), 2),
                "status": "Paid" if (subscription.status or "").lower() == "paid" else "upcoming",
                "provider": _bill_provider(subscription.name),
                "category": "Entertainment",
            }
        )

    deduped_bills = {}
    for bill in bills:
        dedupe_key = (bill["name"], bill["due_date"], bill["amount"])
        deduped_bills[dedupe_key] = bill
    bills = sorted(deduped_bills.values(), key=lambda item: (item["due_date"], item["name"]))

    week_end = now + datetime.timedelta(days=7)
    due_this_week = sum(
        bill["amount"]
        for bill in bills
        if now.date() <= datetime.date.fromisoformat(bill["due_date"]) <= week_end.date()
    )

    return {
        "month": _month_label(selected_year, selected_month),
        "year": selected_year,
        "month_number": selected_month,
        "bills": bills,
        "total_outflow": round(sum(bill["amount"] for bill in bills), 2),
        "due_this_week": round(due_this_week, 2),
        "has_data": bool(bills),
        "source": "mysql_db",
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "data_sources": ["MySQL DB", "Uploaded Statements"],
        "message": None if bills else "No bills detected for this month.",
    }


# ──────────────────────────────────────────────
# CARDS & TRANSACTIONS
# ──────────────────────────────────────────────
def get_cards_data(db: Session, external_id: str) -> dict | None:
    user = get_user_by_external_id(db, external_id)
    if not user:
        return None

    CARD_GRADIENTS = [
        ("#1A2980", "#26D0CE"),
        ("#EB3349", "#F45C43"),
        ("#373B44", "#4286F4"),
        ("#DA4453", "#89216B"),
    ]

    cards = []
    for i, c in enumerate(user.cards):
        cards.append(
            {
                "id": c.id,
                "bank": c.bank_name,
                "type": c.card_type,
                "number": f"•••• {c.last4_digits}",
                "limit": f"₹{c.limit:,.0f}",
                "used": f"₹{c.balance:,.0f}",
                "color1": CARD_GRADIENTS[i % len(CARD_GRADIENTS)][0],
                "color2": CARD_GRADIENTS[i % len(CARD_GRADIENTS)][1],
            }
        )
    base_index = len(cards)
    for j, account in enumerate(user.credit_accounts):
        cards.append(
            {
                "id": 100000 + account.id,
                "bank": account.provider,
                "type": "Credit Line",
                "number": "•••• DEMO",
                "limit": f"₹{account.credit_limit:,.0f}",
                "used": f"₹{account.used_amount:,.0f}",
                "color1": CARD_GRADIENTS[(base_index + j) % len(CARD_GRADIENTS)][0],
                "color2": CARD_GRADIENTS[(base_index + j) % len(CARD_GRADIENTS)][1],
            }
        )

    CATEGORY_EMOJI = {
        "Food & Dining": "🍔", "Shopping": "🛍️", "Travel": "✈️",
        "Subscriptions": "📺", "Salary": "💰", "EMI / Loans": "🏦",
        "Utilities": "💡", "Rent / Housing": "🏠", "Healthcare": "🏥",
        "Cash": "💵", "Investments": "📈", "Tax": "📋",
        "Insurance": "🛡️", "Transfers": "🔄", "Miscellaneous": "📦",
    }

    txs = [
        {
            "name":     t.description,
            "amount":   f"{'-' if t.type == 'debit' else '+'} ₹{t.amount:,.0f}",
            "time":     t.date.strftime("%d %b"),
            "emoji":    CATEGORY_EMOJI.get(t.category, "📦"),
            "category": t.category,
            "type":     t.type,
        }
        for t in sorted(user.transactions, key=lambda x: x.date, reverse=True)[:50]
    ]

    return {
        "cards":        cards,
        "transactions": txs,
        "has_data":     True,
        "source":       "mysql_db",
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ──────────────────────────────────────────────
# CALENDAR
# ──────────────────────────────────────────────
def get_calendar_data(db: Session, external_id: str, year: int, month: int) -> dict | None:
    user = get_user_by_external_id(db, external_id)
    if not user:
        return None

    txs = get_transactions_by_month(db, user.id, year, month)
    daily_spend: dict[int, float] = defaultdict(float)
    for tx in txs:
        if (tx.type or "").lower() != "debit":
            continue
        daily_spend[tx.date.day] += float(tx.amount or 0.0)

    events = [
        {
            "id":       100000 + b.id,
            "date":     b.due_date.day,
            "type":     "bill",
            "tag":      _bill_category(b.name).upper()[:6],
            "title":    b.name,
            "subtitle": f"{_bill_category(b.name)} reminder",
            "amount":   f"₹{b.amount:,.0f}",
        }
        for b in user.bills
        if b.due_date.year == year and b.due_date.month == month
    ]
    events.extend(_build_emi_reminders([loan for loan in user.loans if (loan.status or "").lower() == "active"]))
    events.extend(_build_salary_reminders(txs, year, month))
    events.sort(key=lambda event: (event["date"], event["title"]))

    return {
        "month": _month_label(year, month),
        "year": year,
        "month_number": month,
        "events": events,
        "daily_spend": {str(day): round(amount, 2) for day, amount in sorted(daily_spend.items())},
        "total_month_spend": round(sum(daily_spend.values()), 2),
        "has_data": bool(events or daily_spend),
        "source": "mysql_db",
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "data_sources": ["MySQL DB"],
        "message": None if (events or daily_spend) else "No reminders or spending found for this month.",
    }


# ──────────────────────────────────────────────
# PROFILE
# ──────────────────────────────────────────────
def get_profile_data(db: Session, external_id: str) -> dict | None:
    user = get_user_by_external_id(db, external_id)
    if not user:
        return None

    first_name = user.name.split()[0] if user.name else "User"
    last_name  = user.name.split()[-1] if len(user.name.split()) > 1 else ""
    initials   = (first_name[:1] + last_name[:1]).upper() if last_name else first_name[:2].upper()

    return {
        "user_id":        external_id,
        "first_name":     first_name,
        "last_name":      last_name,
        "full_name":      user.name,
        "initials":       initials,
        "phone":          user.phone_number,
        "email":          user.email,
        "is_onboarded":   True,
        "linked_accounts": [
            {"bank": "Linked MySQL", "type": "Savings", "acc_no": f"•••• {user.id}"}
        ],
        "has_data":       True,
        "source":         "mysql_db",
        "joined_at":      _timestamp_to_iso(user.created_at),
    }

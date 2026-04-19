"""
Dashboard Service Layer — Astra 360
Maps DB models to structured JSON for dashboard screens.
PARTIAL state now surfaces real data with an informational banner.
"""

import calendar
import json
import re
import time
import datetime
from collections import defaultdict
from sqlalchemy import extract
from sqlalchemy.orm import Session
from models import Bill, CalendarEvent, Card, CreditAccount, Subscription, Transaction, User, UserFinancialSummary, UserProcessingStatus, get_user_by_external_id
from services.brain_insights_service import get_latest_insights, prepend_processing_banner
from services.financial_engine import _EMI_IN_DESC, _RENT_IN_DESC, canonical_year_month
from services.user_state import get_user_state


def build_mock_cibil(user: User) -> dict | None:
    """Deterministic mock CIBIL profile — only populated once KYC is complete.

    Numbers stay stable across reloads by seeding off the user's primary key.
    """
    if not getattr(user, "kyc_completed", 0) and not getattr(user, "pan", None):
        return None

    seed = (user.id or 0) * 7919
    score = 730 + (seed % 51)  # 730-780
    loans_count = 1 + (seed % 3)  # 1-3
    cards_count = 3 + ((seed >> 3) % 3)  # 3-5
    utilization = 30 + ((seed >> 5) % 11)  # 30-40%

    return {
        "score": score,
        "loans": loans_count,
        "cards": cards_count,
        "utilization": utilization,
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


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
    if days_until_due < 0:
        return "overdue"
    if days_until_due <= 7:
        return "due-soon"
    return "upcoming"


def _month_label(year: int, month: int) -> str:
    return f"{calendar.month_name[month]} {year}"


_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_TRAILING_REF_RE = re.compile(r"(?:\s+txn[0-9a-z]+|\s+[0-9]{5,})$", re.IGNORECASE)


def _normalize_calendar_title(value: str) -> str:
    text = (value or "").strip().lower()
    text = _TRAILING_REF_RE.sub("", text)
    return _NON_ALNUM_RE.sub("", text)


def _amount_to_float(value: str | float | int | None) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^0-9.\-]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


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


def get_transactions_by_month(db: Session, user_id: int, year: int, month: int) -> list[Transaction]:
    return db.query(Transaction).filter(
        Transaction.user_id == user_id,
        extract("year", Transaction.date) == year,
        extract("month", Transaction.date) == month,
    ).order_by(Transaction.date.asc()).all()


# ──────────────────────────────────────────────
# HOME SUMMARY
# ──────────────────────────────────────────────
def _build_home_insights(
    state: str,
    monthly_income: float,
    monthly_spend: float,
    total_savings: float,
    total_credit_due: float,
    category_dist: dict,
) -> list[dict]:
    """Produce home insights. Tries the LLM for narrative phrasing with strict
    numeric context; always falls back to deterministic rules so the UI never
    renders empty insights during a demo."""
    if state not in ("ACTIVE", "PARTIAL"):
        return []

    top_category = None
    top_amount = 0.0
    if category_dist:
        top_category = max(category_dist, key=category_dist.get)
        top_amount = float(category_dist[top_category])

    savings_rate = (total_savings / monthly_income * 100.0) if monthly_income > 0 else 0.0

    fallback: list[dict] = []
    if state == "PARTIAL":
        fallback.append({
            "id": 1,
            "type": "warning",
            "text": "Your data is being processed. Showing latest snapshot.",
            "time": "Now",
        })
    if monthly_spend > 0:
        fallback.append({
            "id": 2,
            "type": "spend",
            "text": f"You spent {_format_inr(monthly_spend)} this month.",
            "time": "This month",
        })
    if monthly_income > 0:
        rate_label = f"{savings_rate:.0f}%"
        fallback.append({
            "id": 3,
            "type": "info",
            "text": f"You are saving {rate_label} of your income this month.",
            "time": "This month",
        })
    if top_category and top_amount > 0:
        fallback.append({
            "id": 4,
            "type": "info",
            "text": f"Top spend category is {top_category} at {_format_inr(top_amount)}.",
            "time": "This month",
        })
    if total_credit_due > 0:
        fallback.append({
            "id": 5,
            "type": "alert",
            "text": f"Bills due soon: {_format_inr(total_credit_due)}.",
            "time": "Upcoming",
        })

    # Try to get a 3-bullet LLM narrative using ONLY these numbers. The LLM
    # may only rephrase — not recompute. On any failure, keep the rules.
    if monthly_income > 0 or monthly_spend > 0:
        try:
            from services.llm_service import call_llm

            prompt = (
                "Generate exactly 3 short financial insights using ONLY the "
                "numbers below. Do not change or invent any numbers. One "
                "sentence per insight. Output plain text bullets starting "
                "with '- '. No JSON, no headings.\n"
                f"Salary: {monthly_income:.0f}\n"
                f"Expenses: {monthly_spend:.0f}\n"
                f"Savings: {total_savings:.0f}\n"
                f"Savings rate: {savings_rate:.0f}%\n"
                f"Top category: {top_category or 'none'} ({top_amount:.0f})\n"
                f"Bills due: {total_credit_due:.0f}"
            )
            raw = (call_llm(prompt, temperature=0.0) or "").strip()
            bullets = [
                line.lstrip("-• ").strip()
                for line in raw.splitlines()
                if line.strip().startswith(("-", "•"))
            ]
            if len(bullets) >= 1:
                return [
                    {"id": idx + 1, "type": "info", "text": bullet, "time": "This month"}
                    for idx, bullet in enumerate(bullets[:3])
                ]
        except Exception:
            pass

    return fallback[:4]


def get_home_data(db: Session, external_id: str) -> dict | None:
    user = get_user_by_external_id(db, external_id)
    if not user:
        return None

    state   = get_user_state(db, user)
    summary = user.financial_summary
    status  = user.processing_status

    # Balance comes from the summary (built via compute_snapshot_from_transactions,
    # which applies the statement-balance + running-balance guards). Never sum
    # card balances — that produces a meaningless number.
    total_balance      = summary.total_balance if summary else 0.0
    total_savings      = summary.savings if summary else 0.0
    monthly_spend      = summary.monthly_spend if summary else 0.0
    monthly_income     = summary.monthly_income if summary else 0.0
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

    insights = get_latest_insights(db, user, limit=6) if has_data else []
    if is_partial and insights:
        insights = prepend_processing_banner(insights)

    cibil = build_mock_cibil(user)

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
        "savings":           abs(total_savings),
        "monthly_spend":     monthly_spend,
        "investments":       total_investments,
        "credit_due":        total_credit_due,
        "credit_score":      cibil["score"] if cibil else user.credit_score,
        "cibil":             cibil,
        "category_distribution": category_dist,
        "insights":          insights,
        "has_data":          has_data,
        "data_quality_score": summary.data_quality_score if summary else 0.0,
        "source":            "mysql_db",
        "last_updated":      _timestamp_to_iso(datetime.datetime.now()),
        "data_sources":      ["MySQL DB", "Uploaded Statements"] if has_data else ["MySQL DB"],
        "message": (
            None if is_active
            else "Your data is being processed. Showing latest snapshot." if is_partial
            else "Please upload your bank statement to generate insights."
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

    from services.canonical_cards import ensure_canonical_cards

    ensure_canonical_cards(db, user)

    CARD_GRADIENTS = [
        ("#1A2980", "#26D0CE"),
        ("#EB3349", "#F45C43"),
        ("#373B44", "#4286F4"),
        ("#DA4453", "#89216B"),
    ]

    # Aggregate spend per card from canonical-month debits so each card
    # reflects current-month usage, consistent with the snapshot headline.
    canonical = canonical_year_month(user.transactions)
    used_by_card: dict[int, float] = defaultdict(float)
    for tx in user.transactions:
        if (tx.type or "").lower() != "debit" or tx.card_id is None or not tx.date:
            continue
        if canonical is not None and (tx.date.year, tx.date.month) != canonical:
            continue
        used_by_card[tx.card_id] += abs(float(tx.amount or 0.0))

    card_rows = (
        db.query(Card)
        .filter(Card.user_id == user.id)
        .order_by(Card.id.asc())
        .all()
    )
    cards = []
    for i, c in enumerate(card_rows):
        used_amount = round(used_by_card.get(c.id, float(c.balance or 0.0)), 2)
        cards.append(
            {
                "id": c.id,
                "bank": c.bank_name,
                "type": c.card_type,
                "number": f"•••• {c.last4_digits}",
                "limit": f"₹{c.limit:,.0f}",
                "used": f"₹{used_amount:,.0f}",
                "color1": CARD_GRADIENTS[i % len(CARD_GRADIENTS)][0],
                "color2": CARD_GRADIENTS[i % len(CARD_GRADIENTS)][1],
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
            "card_id":  t.card_id,
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

    for sub in user.subscriptions:
        next_billing = sub.next_billing_date
        if not next_billing or next_billing.year != year or next_billing.month != month:
            continue
        events.append(
            {
                "id":       400000 + sub.id,
                "date":     next_billing.day,
                "type":     "subscription",
                "tag":      "SUB",
                "title":    sub.name,
                "subtitle": f"{sub.billing_cycle or 'monthly'} renewal".title(),
                "amount":   f"₹{sub.amount:,.0f}",
            }
        )

    stored_events = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user.id,
            extract("year", CalendarEvent.event_date) == year,
            extract("month", CalendarEvent.event_date) == month,
        )
        .all()
    )
    known_titles = {event["title"].lower() for event in events}
    for stored in stored_events:
        title = (stored.title or "").strip()
        if not title or title.lower() in known_titles:
            continue
        events.append(
            {
                "id":       500000 + stored.id,
                "date":     stored.event_date.day,
                "type":     stored.event_type or "event",
                "tag":      (stored.event_type or "EVT").upper()[:6],
                "title":    title,
                "subtitle": f"{(stored.event_type or 'event').title()} reminder",
                "amount":   f"₹{stored.amount:,.0f}",
            }
        )

    semantic_signatures: set[tuple[int, str, float]] = set()
    for event in events:
        title = str(event.get("title", ""))
        tag = str(event.get("tag", "")).upper()
        amount = round(abs(_amount_to_float(event.get("amount"))), 2)
        day = int(event.get("date", 0) or 0)
        if day <= 0 or amount <= 0:
            continue
        lowered = title.lower()
        if "rent" in lowered or tag == "RENT":
            semantic_signatures.add((day, "rent", amount))
        if "emi" in lowered or "nach" in lowered or tag == "EMI":
            semantic_signatures.add((day, "emi", amount))

    # Rent / EMI from raw debits (narration), so the calendar fills even when
    # commitment-derived Bill rows are missing or delayed.
    known_titles = {event["title"].lower() for event in events}
    for tx in txs:
        if (tx.type or "").lower() != "debit" or not tx.date:
            continue
        raw = (tx.description or "").strip()
        if not raw:
            continue
        tag = None
        if _RENT_IN_DESC.search(raw):
            tag = "RENT"
        elif _EMI_IN_DESC.search(raw):
            tag = "EMI"
        else:
            continue
        amount = round(abs(float(tx.amount or 0.0)), 2)
        kind = "rent" if tag == "RENT" else "emi"
        signature = (tx.date.day, kind, amount)
        if signature in semantic_signatures:
            continue
        semantic_signatures.add(signature)
        title = raw[:200]
        if title.lower() in known_titles:
            continue
        known_titles.add(title.lower())
        events.append(
            {
                "id":       600_000_000 + int(tx.id),
                "date":     tx.date.day,
                "type":     "bill",
                "tag":      tag,
                "title":    title,
                "subtitle": "Recurring debit",
                "amount":   f"₹{amount:,.0f}",
            }
        )

    # Salary credits timeline from raw transactions (visible income history).
    salary_titles: set[tuple[int, str, float]] = set()
    for event in events:
        if str(event.get("tag", "")).upper() != "SAL":
            continue
        amount = round(abs(_amount_to_float(event.get("amount"))), 2)
        day = int(event.get("date", 0) or 0)
        if amount > 0 and day > 0:
            salary_titles.add((day, _normalize_calendar_title(str(event.get("title", ""))), amount))

    for tx in txs:
        if (tx.type or "").lower() != "credit" or not tx.date:
            continue
        raw = (tx.description or "").strip()
        if not raw:
            continue
        if "salary" not in raw.lower() and "payroll" not in raw.lower():
            continue
        amount = round(abs(float(tx.amount or 0.0)), 2)
        title = raw[:200]
        salary_key = (tx.date.day, _normalize_calendar_title(title), amount)
        if salary_key in salary_titles:
            continue
        salary_titles.add(salary_key)
        events.append(
            {
                "id":       700_000_000 + int(tx.id),
                "date":     tx.date.day,
                "type":     "income",
                "tag":      "SAL",
                "title":    title,
                "subtitle": "Salary credit",
                "amount":   f"+₹{amount:,.0f}",
            }
        )

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
            {"bank": "Kotak Mahindra Bank", "short_name": "KOTAK", "type": "Savings", "acc_no": "•••• 5821"}
        ],
        "has_data":       True,
        "source":         "mysql_db",
        "joined_at":      _timestamp_to_iso(user.created_at),
    }

"""
Dashboard Service Layer — Phase 3
Fetches real data from MySQL using SQLAlchemy models.
Maps DB objects to structured JSON for dashboard screens.
"""

import time
import datetime
from sqlalchemy.orm import Session
from models import User, Transaction, Card, Loan, Bill, get_user_by_external_id, UserFinancialSummary, UserProcessingStatus
from services.user_state import get_user_state

def _timestamp_to_iso(ts):
    """Convert unix timestamp or datetime to ISO string."""
    if ts is None:
        return None
    if isinstance(ts, (int, float)):
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))
    return ts.strftime("%Y-%m-%dT%H:%M:%S")

# ----------------------------------------------
# HOME SUMMARY
# ----------------------------------------------
def get_home_data(db: Session, external_id: str) -> dict | None:
    user = get_user_by_external_id(db, external_id)
    if not user:
        return None

    # 1. Determine State
    state = get_user_state(db, user)
    
    # 2. Fetch Summary & Status
    summary = user.financial_summary
    status = user.processing_status
    
    # 3. Calculate metrics from real data
    total_balance = summary.total_balance if summary else sum(card.balance for card in user.cards)
    total_savings = summary.savings if summary else 0.0
    total_investments = 0.0 # Placeholder until we have investment parsing
    total_credit_due = sum(bill.amount for bill in user.bills if bill.status != "paid")

    first_name = user.name.split()[0] if user.name else "User"
    last_name = user.name.split()[-1] if len(user.name.split()) > 1 else ""
    initials = (first_name[:1] + last_name[:1]).upper() if last_name else first_name[:2].upper()

    return {
        "user_id": external_id,
        "state": state,
        "activation_required": state != "ACTIVE",
        "processing_status": {
            "status": status.status if status else "idle",
            "progress": status.progress if status else 0,
            "stage": status.stage if status else "Waiting for data"
        } if state != "ACTIVE" else None,
        "first_name": first_name,
        "last_name": last_name,
        "initials": initials,
        "balance": total_balance,
        "savings": total_savings,
        "investments": total_investments,
        "credit_due": total_credit_due,
        "credit_score": user.credit_score,
        "insights": [
            {"id": 1, "type": "info", "text": f"Welcome back, {first_name}! Your profile is {state.lower()}.", "time": "Now"}
        ] if state == "ACTIVE" else [],
        "has_data": state == "ACTIVE",
        "data_quality_score": summary.data_quality_score if summary else 0.0,
        "source": "mysql_db",
        "last_updated": _timestamp_to_iso(datetime.datetime.now()),
        "data_sources": ["MySQL DB", "Uploaded Statements"] if state == "ACTIVE" else ["MySQL DB"],
        "message": None if state == "ACTIVE" else "Please upload your bank statement to activate insights."
    }

# ----------------------------------------------
# BILLS & SUBSCRIPTIONS
# ----------------------------------------------
def get_bills_data(db: Session, external_id: str) -> dict | None:
    user = get_user_by_external_id(db, external_id)
    if not user:
        return None

    bills = []
    for b in user.bills:
        bills.append({
            "name": b.name,
            "amount": b.amount,
            "due_date": b.due_date.strftime("%d %b %Y"),
            "status": b.status.capitalize()
        })

    return {
        "subscriptions": [], # Simplified for now
        "utilities": bills,
        "total_monthly": sum(b.amount for b in user.bills),
        "due_this_week": sum(b.amount for b in user.bills if b.status != "paid"),
        "has_data": True,
        "source": "mysql_db",
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "data_sources": ["MySQL DB"],
    }

# ----------------------------------------------
# CARDS & TRANSACTIONS
# ----------------------------------------------
def get_cards_data(db: Session, external_id: str) -> dict | None:
    user = get_user_by_external_id(db, external_id)
    if not user:
        return None

    cards = []
    for c in user.cards:
        cards.append({
            "id": c.id,
            "bank": c.bank_name,
            "type": c.card_type,
            "number": f"•••• {c.last4_digits}",
            "limit": f"₹{c.limit:,.0f}",
            "used": f"₹{c.balance:,.0f}",
            "color1": "#1A2980" if c.id % 2 == 0 else "#EB3349",
            "color2": "#26D0CE" if c.id % 2 == 0 else "#F45C43",
        })

    txs = []
    for t in user.transactions:
        txs.append({
            "name": t.description,
            "amount": f"{'-' if t.type == 'debit' else '+'} ₹{t.amount:,.0f}",
            "time": t.date.strftime("%d %b"),
            "emoji": "💰" if t.type == "credit" else "📦",
            "category": t.category
        })

    return {
        "cards": cards,
        "transactions": txs,
        "has_data": True,
        "source": "mysql_db",
        "last_updated": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

# ----------------------------------------------
# CALENDAR
# ----------------------------------------------
def get_calendar_data(db: Session, external_id: str) -> dict | None:
    user = get_user_by_external_id(db, external_id)
    if not user:
        return None

    events = []
    for b in user.bills:
        events.append({
            "id": b.id,
            "date": b.due_date.day,
            "type": "bill",
            "tag": b.name.split()[0].upper(),
            "title": b.name,
            "subtitle": "Due Payment",
            "amount": f"₹{b.amount:,.0f}"
        })

    return {
        "events": events,
        "has_data": True,
        "source": "mysql_db",
    }

# ----------------------------------------------
# PROFILE
# ----------------------------------------------
def get_profile_data(db: Session, external_id: str) -> dict | None:
    user = get_user_by_external_id(db, external_id)
    if not user:
        return None

    first_name = user.name.split()[0] if user.name else "User"
    last_name = user.name.split()[-1] if len(user.name.split()) > 1 else ""
    initials = (first_name[:1] + last_name[:1]).upper() if last_name else first_name[:2].upper()

    return {
        "user_id": external_id,
        "first_name": first_name,
        "last_name": last_name,
        "full_name": user.name,
        "initials": initials,
        "phone": user.phone_number,
        "email": user.email,
        "is_onboarded": True,
        "linked_accounts": [
            {"bank": "Linked MySQL", "type": "Savings", "acc_no": f"•••• {user.id}"}
        ],
        "has_data": True,
        "source": "mysql_db",
        "joined_at": _timestamp_to_iso(user.created_at),
    }


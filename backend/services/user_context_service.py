"""Live user context builder for the chat LLM prompts.

The previous chat pipeline only fed the global knowledge base chunks to
the LLM, which made non-finance answers feel canned because the model
had no visibility into the user's actual situation (income, top spend
categories, commitments, upcoming bills, subscriptions). This module
gathers a compact, PII-safe snapshot from the database on every turn so
insurance / tax / scam agents can give truly personalized answers that
reflect the latest uploaded statement.

Design constraints:
- Never include raw transaction rows or phone/email/PAN.
- Stay short (~800 chars max) so it fits any model context window.
- Reflect the canonical month from the finance snapshot (no drift).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from models import Bill, CalendarEvent, Subscription, User
from services.financial_engine import (
    FinancialSnapshot,
    _format_month_label,
    build_financial_snapshot,
)


def _safe_list(items: List[Any]) -> List[Any]:
    return list(items or [])


def _format_inr(amount: float) -> str:
    return f"Rs {amount:,.0f}"


def _upcoming_bills(db: Session, user: User, horizon_days: int = 30) -> List[Dict[str, Any]]:
    now = dt.datetime.utcnow()
    cutoff = now + dt.timedelta(days=horizon_days)
    bills = (
        db.query(Bill)
        .filter(
            Bill.user_id == user.id,
            Bill.status != "paid",
            Bill.due_date >= now,
            Bill.due_date <= cutoff,
        )
        .order_by(Bill.due_date.asc())
        .limit(5)
        .all()
    )
    return [
        {
            "name": bill.name,
            "amount": float(bill.amount or 0.0),
            "due_date": bill.due_date.strftime("%Y-%m-%d") if bill.due_date else None,
            "status": bill.status,
        }
        for bill in bills
    ]


def _active_subscriptions(db: Session, user: User) -> List[Dict[str, Any]]:
    subs = (
        db.query(Subscription)
        .filter(Subscription.user_id == user.id, Subscription.status == "active")
        .order_by(Subscription.amount.desc())
        .limit(5)
        .all()
    )
    return [
        {
            "name": sub.name,
            "amount": float(sub.amount or 0.0),
            "cycle": sub.billing_cycle or "monthly",
        }
        for sub in subs
    ]


def _upcoming_events(db: Session, user: User, horizon_days: int = 14) -> List[Dict[str, Any]]:
    now = dt.datetime.utcnow()
    cutoff = now + dt.timedelta(days=horizon_days)
    events = (
        db.query(CalendarEvent)
        .filter(
            CalendarEvent.user_id == user.id,
            CalendarEvent.event_date >= now,
            CalendarEvent.event_date <= cutoff,
        )
        .order_by(CalendarEvent.event_date.asc())
        .limit(5)
        .all()
    )
    return [
        {
            "title": event.title,
            "type": event.event_type,
            "amount": float(event.amount or 0.0),
            "date": event.event_date.strftime("%Y-%m-%d") if event.event_date else None,
        }
        for event in events
    ]


def _snapshot_facts(snapshot: FinancialSnapshot) -> Dict[str, Any]:
    if not snapshot.transactions_found:
        return {
            "has_transactions": False,
            "message": "User has not uploaded a bank statement yet.",
        }
    return {
        "has_transactions": True,
        "month_label": _format_month_label(snapshot),
        "salary": snapshot.salary,
        "expenses": snapshot.expenses,
        "savings": snapshot.savings,
        "savings_rate_pct": (
            round((snapshot.savings / snapshot.salary) * 100.0, 1)
            if snapshot.salary > 0
            else None
        ),
        "top_category": snapshot.top_category,
        "top_category_amount": snapshot.top_category_amount,
        "top_categories": [
            {"name": name, "amount": amount}
            for name, amount in (snapshot.top_categories or [])[:3]
        ],
        "rent_total": snapshot.rent_total,
        "emi_total": snapshot.emi_total,
        "subscriptions_total": snapshot.subscriptions_total,
        "total_balance": snapshot.total_balance,
    }


def build_user_context(db: Session, user: User) -> Dict[str, Any]:
    """Build the live user-context dict used by non-finance agents.

    Returned keys:
      - ``profile``: name, credit score, risk level
      - ``finance``: salary / expenses / savings / top category / commitments
      - ``bills``: up to 5 upcoming unpaid bills
      - ``subscriptions``: up to 5 active subscriptions
      - ``events``: up to 5 upcoming calendar events
      - ``keys``: ordered list of populated sections (for telemetry)
      - ``prompt_text``: pre-formatted text block the LLM can consume directly
    """

    snapshot = build_financial_snapshot(db, user)
    finance = _snapshot_facts(snapshot)
    bills = _upcoming_bills(db, user)
    subs = _active_subscriptions(db, user)
    events = _upcoming_events(db, user)

    profile = {
        "name": user.name,
        "credit_score": user.credit_score or None,
        "risk_level": user.risk_level,
        "monthly_income_declared": float(user.monthly_income or 0.0) or None,
    }

    keys: List[str] = ["profile"]
    if finance.get("has_transactions"):
        keys.append("finance")
    if bills:
        keys.append("bills")
    if subs:
        keys.append("subscriptions")
    if events:
        keys.append("events")

    prompt_text = _render_prompt_text(profile, finance, bills, subs, events)

    return {
        "profile": profile,
        "finance": finance,
        "bills": _safe_list(bills),
        "subscriptions": _safe_list(subs),
        "events": _safe_list(events),
        "keys": keys,
        "prompt_text": prompt_text,
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds"),
    }


def _render_prompt_text(
    profile: Dict[str, Any],
    finance: Dict[str, Any],
    bills: List[Dict[str, Any]],
    subs: List[Dict[str, Any]],
    events: List[Dict[str, Any]],
) -> str:
    lines: List[str] = ["USER SNAPSHOT (live from database):"]

    name = profile.get("name") or "User"
    credit = profile.get("credit_score")
    risk = profile.get("risk_level")
    lines.append(
        f"- Profile: name={name}"
        + (f", credit_score={credit}" if credit else "")
        + (f", risk_level={risk}" if risk else "")
    )

    if finance.get("has_transactions"):
        rate = finance.get("savings_rate_pct")
        lines.append(
            f"- Finance ({finance.get('month_label')}): "
            f"salary={_format_inr(finance.get('salary', 0))}, "
            f"expenses={_format_inr(finance.get('expenses', 0))}, "
            f"savings={_format_inr(finance.get('savings', 0))}"
            + (f" ({rate}% of salary)" if rate is not None else "")
        )
        top_cat = finance.get("top_category")
        if top_cat:
            lines.append(
                f"- Top spend: {top_cat} at {_format_inr(finance.get('top_category_amount', 0))}"
            )
        commitments = []
        if finance.get("rent_total", 0) > 0:
            commitments.append(f"rent {_format_inr(finance['rent_total'])}")
        if finance.get("emi_total", 0) > 0:
            commitments.append(f"EMI {_format_inr(finance['emi_total'])}")
        if finance.get("subscriptions_total", 0) > 0:
            commitments.append(
                f"subscriptions {_format_inr(finance['subscriptions_total'])}/mo"
            )
        if commitments:
            lines.append(f"- Monthly commitments: {', '.join(commitments)}")
    else:
        lines.append("- Finance: no bank statement uploaded yet.")

    if bills:
        head = ", ".join(
            f"{b['name']} ({_format_inr(b['amount'])} on {b['due_date']})" for b in bills[:3]
        )
        lines.append(f"- Upcoming bills: {head}")

    if subs:
        head = ", ".join(f"{s['name']} {_format_inr(s['amount'])}" for s in subs[:3])
        lines.append(f"- Active subscriptions: {head}")

    if events:
        head = ", ".join(f"{e['title']} on {e['date']}" for e in events[:3])
        lines.append(f"- Upcoming events: {head}")

    return "\n".join(lines)

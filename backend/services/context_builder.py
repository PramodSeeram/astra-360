import logging
from sqlalchemy.orm import Session
from models import Card, User, Transaction
from services.canonical_cards import ensure_canonical_cards
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

SPENDING_CATEGORIES = ("Food", "Shopping", "Transport", "Utilities", "Bills", "Entertainment", "Other")


def _money(value: Optional[float]) -> float:
    return round(float(value or 0.0), 2)


def build_user_context(db: Session, user: User) -> Dict[str, Any]:
    """
    Summarizes user financial data for the LLM.
    Limits data size to keep prompts efficient.
    """
    ensure_canonical_cards(db, user)

    # 1. Profile Summary
    profile = {
        "name": user.name,
        "credit_score": user.credit_score if user.credit_score and user.credit_score > 0 else None,
        "income": _money(user.monthly_income) if user.monthly_income and user.monthly_income > 0 else None,
        "risk_level": user.risk_level if user.risk_level and user.risk_level.lower() != "unknown" else None
    }

    # 2. Cards Summary (Limit 2)
    cards_data = []
    total_credit_limit = 0.0
    total_card_balance = 0.0

    card_rows = (
        db.query(Card)
        .filter(Card.user_id == user.id)
        .order_by(Card.id.asc())
        .all()
    )
    for card in card_rows:
        total_credit_limit += card.limit or 0.0
        total_card_balance += card.balance or 0.0
    for account in user.credit_accounts:
        total_credit_limit += account.credit_limit or 0.0
        total_card_balance += account.used_amount or 0.0

    for card in card_rows[:3]:
        card_limit = card.limit or 0.0
        card_balance = card.balance or 0.0
        utilization = (card_balance / card_limit * 100) if card_limit > 0 else 0
        cards_data.append({
            "bank": card.bank_name,
            "type": card.card_type,
            "last4": card.last4_digits,
            "limit": _money(card_limit),
            "used": _money(card_balance),
            "utilization_pct": round(utilization, 1),
        })
    if not cards_data:
        for account in user.credit_accounts[:2]:
            account_limit = account.credit_limit or 0.0
            account_used = account.used_amount or 0.0
            utilization = (account_used / account_limit * 100) if account_limit > 0 else 0
            cards_data.append({
                "bank": account.provider,
                "type": "Credit Line",
                "limit": _money(account_limit),
                "used": _money(account_used),
                "utilization_pct": round(utilization, 1),
                "key_offers": "Monitor usage and repay before statement date"
            })

    credit_utilization = (
        round((total_card_balance / total_credit_limit) * 100, 1)
        if total_credit_limit > 0
        else None
    )

    # 3. Loans Summary (Limit 2)
    loans_data = []
    total_monthly_emi = sum(loan.emi or 0.0 for loan in user.loans)
    for loan in user.loans[:2]:
        loans_data.append({
            "type": loan.loan_type,
            "emi": _money(loan.emi),
            "rate": f"{loan.interest_rate}%",
            "remaining": _money(loan.remaining_amount)
        })

    # 4. Spending Summary (Last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_transactions = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.date >= thirty_days_ago
    ).order_by(Transaction.date.desc()).all()

    spending_transactions = [
        t for t in recent_transactions
        if (t.type or "").lower() == "debit" and (t.category or "") != "Transfers"
    ]
    total_spend = sum(t.amount or 0.0 for t in spending_transactions)

    # Category summary
    categories = {category: 0.0 for category in SPENDING_CATEGORIES}
    for t in spending_transactions:
        category = t.category if t.category in categories else "Other"
        categories[category] += t.amount or 0.0

    top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]
    top_cat_list = [f"{cat}: {_money(amt)}" for cat, amt in top_categories if amt > 0]

    # 5. Alerts & Ratios
    debt_to_income = (
        round((total_monthly_emi / user.monthly_income) * 100, 1)
        if user.monthly_income and user.monthly_income > 0
        else None
    )

    alerts = []
    insights = []
    recommended_actions = []

    if credit_utilization is not None and credit_utilization > 70:
        alerts.append("High Card Utilization (>70%)")
        insights.append(f"Credit utilization is high at {credit_utilization}%.")
        recommended_actions.append("Reduce credit utilization below 30% before adding new card spends.")
    elif credit_utilization is not None and credit_utilization > 30:
        insights.append(f"Credit utilization is above the ideal 30% level at {credit_utilization}%.")
        recommended_actions.append("Pay down card balance until utilization is below 30%.")

    if debt_to_income is not None and debt_to_income > 40:
        alerts.append("High debt-to-income ratio (>40%)")
        insights.append(f"EMIs consume {debt_to_income}% of monthly income.")
        recommended_actions.append("Avoid new EMIs until the EMI-to-income ratio falls below 40%.")
    if user.credit_score and user.credit_score < 600:
        alerts.append("Credit score needs improvement")
        insights.append(f"Credit score is low at {user.credit_score}.")
        recommended_actions.append("Prioritize on-time payments and reduce overdue balances.")

    if top_cat_list:
        top_category, top_amount = top_categories[0]
        insights.append(f"Top spending category is {top_category} at ₹{_money(top_amount)}.")
        if top_amount > 0:
            recommended_actions.append(f"Set a monthly cap for {top_category} below ₹{_money(top_amount * 0.9)}.")

    if user.subscriptions:
        monthly_subscription_total = sum(sub.amount or 0.0 for sub in user.subscriptions)
        insights.append(f"Detected {len(user.subscriptions)} subscription payments totaling ₹{_money(monthly_subscription_total)}.")
        recommended_actions.append("Review unused subscriptions and cancel the lowest-value plan first.")

    savings = max(0.0, (profile["income"] or 0.0) - total_spend - total_monthly_emi)
    if profile["income"] and savings < profile["income"] * 0.1:
        insights.append("Estimated savings are below 10% of income.")
        recommended_actions.append("Move at least 10% of income to savings at the start of the month.")

    if not insights:
        insights.append("I don't have enough data to identify a strong financial pattern yet.")
    if not recommended_actions:
        recommended_actions.append("Upload more recent transactions to unlock specific recommendations.")

    context = {
        "profile": profile,
        "cards": cards_data,
        "loans": loans_data,
        "loan_summary": {
            "total_emi": _money(total_monthly_emi),
            "debt_to_income_ratio": f"{debt_to_income}%" if debt_to_income is not None else None
        },
        "credit_summary": {
            "score": profile["credit_score"],
            "utilization": credit_utilization,
            "risk": profile["risk_level"],
            "total_limit": _money(total_credit_limit),
            "used": _money(total_card_balance),
            "credit_score": profile["credit_score"],
            "used_credit": _money(total_card_balance),
            "emi": _money(total_monthly_emi),
        } if (total_credit_limit > 0 or total_card_balance > 0 or profile["credit_score"]) else {
            "credit_score": None,
            "total_limit": 0,
            "used_credit": 0,
            "emi": 0,
            "utilization": None,
            "score": None,
            "risk": profile["risk_level"],
            "used": 0,
        },
        "financial_profile": {
            "total_spending": _money(total_spend),
            "emi": _money(total_monthly_emi),
            "credit_utilization": credit_utilization,
        },
        "spending_summary": {
            "monthly_spend": _money(total_spend),
            "top_categories": top_cat_list,
            "savings": _money(savings)
        },
        "spending_breakdown": {category: _money(amount) for category, amount in categories.items()},
        "insights": insights[:4],
        "recommended_actions": recommended_actions[:4],
        "alerts": alerts
    }

    return context

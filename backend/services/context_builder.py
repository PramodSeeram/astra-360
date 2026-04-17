import logging
from sqlalchemy.orm import Session
from models import User, Card, Loan, Transaction, Bill
from typing import Dict, Any, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def build_user_context(db: Session, user: User) -> Dict[str, Any]:
    """
    Summarizes user financial data for the LLM.
    Limits data size to keep prompts efficient.
    """
    
    # 1. Profile Summary
    profile = {
        "name": user.name,
        "credit_score": user.credit_score or 500,
        "income": user.monthly_income or 0.0,
        "risk_level": user.risk_level or "Unknown"
    }

    # 2. Cards Summary (Limit 2)
    cards_data = []
    total_credit_limit = 0.0
    total_card_balance = 0.0
    
    for card in user.cards[:2]:
        utilization = (card.balance / card.limit * 100) if card.limit > 0 else 0
        cards_data.append({
            "bank": card.bank_name,
            "type": card.card_type,
            "limit": card.limit,
            "used": card.balance,
            "utilization_pct": round(utilization, 1),
            "key_offers": "10% off on Amazon" if "HDFC" in card.bank_name else "5x points on dining"
        })
        total_credit_limit += card.limit
        total_card_balance += card.balance
    
    # 3. Loans Summary (Limit 2)
    loans_data = []
    total_monthly_emi = 0.0
    for loan in user.loans[:2]:
        loans_data.append({
            "type": loan.loan_type,
            "emi": loan.emi,
            "rate": f"{loan.interest_rate}%",
            "remaining": loan.remaining_amount
        })
        total_monthly_emi += loan.emi

    # 4. Spending Summary (Last 30 days)
    thirty_days_ago = datetime.utcnow() - timedelta(days=30)
    recent_transactions = db.query(Transaction).filter(
        Transaction.user_id == user.id,
        Transaction.date >= thirty_days_ago
    ).order_by(Transaction.date.desc()).all()

    total_spend = sum(t.amount for t in recent_transactions if t.type.lower() == "debit")
    
    # Category summary
    categories = {}
    for t in recent_transactions:
        if t.type.lower() == "debit":
            categories[t.category] = categories.get(t.category, 0) + t.amount
    
    top_categories = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]
    top_cat_list = [f"{cat}: {amt}" for cat, amt in top_categories]

    # 5. Alerts & Ratios
    debt_to_income = (total_monthly_emi / user.monthly_income * 100) if user.monthly_income > 0 else 0
    
    alerts = []
    if any(c["utilization_pct"] > 70 for c in cards_data):
        alerts.append("High Card Utilization (>70%)")
    if debt_to_income > 40:
        alerts.append("High debt-to-income ratio (>40%)")
    if user.credit_score and user.credit_score < 600:
        alerts.append("Credit score needs improvement")

    context = {
        "profile": profile,
        "cards": cards_data,
        "loans": loans_data,
        "loan_summary": {
            "total_emi": total_monthly_emi,
            "debt_to_income_ratio": f"{round(debt_to_income, 1)}%"
        },
        "spending_summary": {
            "monthly_spend": total_spend,
            "top_categories": top_cat_list,
            "savings": max(0, profile["income"] - total_spend - total_monthly_emi)
        },
        "alerts": alerts
    }

    return context

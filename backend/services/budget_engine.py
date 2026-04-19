"""Deterministic monthly budget from transactions (Phase 2).

Delegates to ``financial_engine.compute_snapshot_from_transactions`` so chat,
dashboard, and budget agent stay numerically aligned.
"""

from __future__ import annotations

from typing import Any, Dict, List

from models import Transaction

from services.financial_engine import (
    compute_snapshot_from_transactions,
    snapshot_category_distribution,
)


def compute_monthly_budget(transactions: List[Transaction]) -> Dict[str, Any]:
    """Return income vs expenses, savings, and per-month breakdown from bank data.

    ``income`` is the snapshot's estimated monthly salary (3-month average rule).
    ``expenses`` / ``savings`` refer to the canonical headline month.
    """
    snapshot = compute_snapshot_from_transactions(transactions)
    if not snapshot.transactions_found:
        return {
            "transactions_found": False,
            "headline_month": None,
            "income": 0.0,
            "expenses": 0.0,
            "savings": 0.0,
            "total_balance": 0.0,
            "category_breakdown": {},
            "by_month": [],
            "top_category": None,
            "top_category_amount": 0.0,
        }

    category_breakdown = snapshot_category_distribution(transactions, snapshot)

    return {
        "transactions_found": True,
        "headline_month": snapshot.headline_month,
        "income": float(snapshot.salary or 0.0),
        "expenses": float(snapshot.expenses or 0.0),
        "savings": float(snapshot.savings or 0.0),
        "total_balance": float(snapshot.total_balance or 0.0),
        "category_breakdown": {k: round(float(v), 2) for k, v in category_breakdown.items()},
        "by_month": list(snapshot.monthly_breakdown or []),
        "top_category": snapshot.top_category,
        "top_category_amount": float(snapshot.top_category_amount or 0.0),
        "salary_months_used": list(snapshot.salary_months_used or []),
        "rent_total": float(snapshot.rent_total or 0.0),
        "emi_total": float(snapshot.emi_total or 0.0),
        "subscriptions_total": float(snapshot.subscriptions_total or 0.0),
    }

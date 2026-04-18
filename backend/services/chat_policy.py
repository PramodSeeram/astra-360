"""Single place for user-facing chat policy strings and the canonical
response envelope used across every agent.

Why this module exists:
- All ``"Not found in knowledge base"`` / activation / fallback copy
  used to live inline inside routes and services, which made chat
  replies look hardcoded and impossible to tune centrally.
- Every agent now emits the same envelope shape, so the UI can trust
  ``reason``, ``confidence``, and ``sources`` without special casing.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


CHAT_RESPONSE_KEYS = (
    "type",
    "response",
    "ui_action",
    "actions",
    "sources",
    "confidence",
    "reason",
    "data",
)


ACTIVATION_REQUIRED_RESPONSE: Dict[str, Any] = {
    "type": "activation_required",
    "response": (
        "Your data is being processed. Showing the latest snapshot while "
        "we finish parsing your statement."
    ),
    "ui_action": "open_file_upload",
    "actions": ["upload_now", "how_it_works"],
    "sources": [],
    "confidence": 0.3,
    "reason": "partial_activation",
    "data": {},
}


FINANCE_NO_DATA_RESPONSE: Dict[str, Any] = {
    "type": "finance_agent",
    "response": "Please upload your bank statement to generate insights.",
    "ui_action": "open_file_upload",
    "actions": ["upload_now"],
    "sources": [],
    "confidence": 0.4,
    "reason": "finance_no_data",
    "data": {},
}


def build_response_envelope(
    type_name: str,
    response: str,
    sources: Optional[List[str]] = None,
    reason: str = "ok",
    confidence: Optional[float] = None,
    route: Any = None,
    data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Return the canonical chat envelope all agents must produce."""

    envelope: Dict[str, Any] = {
        "type": type_name,
        "response": response,
        "ui_action": None,
        "actions": [],
        "sources": list(sources or []),
        "confidence": confidence,
        "reason": reason,
        "data": dict(data or {}),
    }
    if route is not None:
        envelope["data"].setdefault(
            "route",
            {
                "agent": getattr(route, "agent", None),
                "category": getattr(route, "category", None),
                "reason": getattr(route, "reason", None),
                "confidence": getattr(route, "confidence", None),
            },
        )
    return envelope


def finance_snapshot_data(snapshot: Any) -> Dict[str, Any]:
    """Strict whitelist of snapshot fields safe to return to the UI."""
    if not getattr(snapshot, "transactions_found", False):
        return {}
    return {
        "salary": snapshot.salary,
        "expenses": snapshot.expenses,
        "savings": snapshot.savings,
        "total_balance": snapshot.total_balance,
        "headline_month": snapshot.headline_month,
        "top_category": snapshot.top_category,
        "top_category_amount": snapshot.top_category_amount,
        "subscriptions_total": snapshot.subscriptions_total,
    }


def finance_sources(snapshot: Any) -> List[str]:
    return ["db"] if getattr(snapshot, "transactions_found", False) else []

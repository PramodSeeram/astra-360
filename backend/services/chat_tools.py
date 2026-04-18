"""Tool implementations for agentic chat.

Numbers always come from the database or RAG — never from the LLM.
These functions are the only "hands" the planner may invoke.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models import Transaction, User
from services.financial_engine import (
    build_financial_snapshot,
    snapshot_category_distribution,
    transactions_in_month,
)
from services.knowledge_base_service import retrieve_context
from services.user_context_service import build_user_context


def tool_get_financial_summary(db: Session, user: User) -> Dict[str, Any]:
    snap = build_financial_snapshot(db, user)
    if not snap.transactions_found:
        return {"ok": True, "has_data": False, "message": "No transactions in database."}
    return {
        "ok": True,
        "has_data": True,
        "headline_month": snap.headline_month,
        "salary_3mo_avg": snap.salary,
        "expenses_canonical_month": snap.expenses,
        "savings_canonical_month": snap.savings,
        "total_balance": snap.total_balance,
        "top_category": snap.top_category,
        "top_category_amount": snap.top_category_amount,
        "subscriptions_monthly_estimate": snap.subscriptions_total,
        "rent_this_month": snap.rent_total,
        "emi_this_month": snap.emi_total,
        "top_categories": [{"name": n, "amount": a} for n, a in (snap.top_categories or [])[:10]],
        "subscription_line_items": list(snap.subscriptions_items or [])[:10],
        "largest_debits": list(snap.top_debits or [])[:10],
    }


def tool_get_top_categories(db: Session, user: User, limit: int = 5) -> Dict[str, Any]:
    limit = max(1, min(20, int(limit)))
    snap = build_financial_snapshot(db, user)
    if not snap.transactions_found or snap.current_year is None:
        return {"ok": True, "has_data": False, "categories": []}
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    dist = snapshot_category_distribution(txs, snap)
    ordered = sorted(dist.items(), key=lambda x: x[1], reverse=True)[:limit]
    return {
        "ok": True,
        "has_data": True,
        "headline_month": snap.headline_month,
        "limit": limit,
        "categories": [{"name": n, "amount": a} for n, a in ordered],
    }


def tool_get_top_debit_transactions(db: Session, user: User, limit: int = 5) -> Dict[str, Any]:
    limit = max(1, min(50, int(limit)))
    snap = build_financial_snapshot(db, user)
    if not snap.transactions_found or snap.current_year is None or snap.current_month is None:
        return {"ok": True, "has_data": False, "transactions": []}
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    month_txs = transactions_in_month(txs, snap.current_year, snap.current_month)
    debits = [
        tx
        for tx in month_txs
        if (tx.type or "").lower() == "debit" and tx.date
    ]
    debits.sort(key=lambda t: abs(float(t.amount or 0.0)), reverse=True)
    out: List[Dict[str, Any]] = []
    for tx in debits[:limit]:
        out.append(
            {
                "date": tx.date.strftime("%Y-%m-%d") if tx.date else None,
                "amount": round(abs(float(tx.amount or 0.0)), 2),
                "description": (tx.description or "")[:200],
                "category": tx.category or "Other",
            }
        )
    return {
        "ok": True,
        "has_data": True,
        "headline_month": snap.headline_month,
        "limit": limit,
        "transactions": out,
    }


def tool_get_recent_transactions(
    db: Session,
    user: User,
    limit: int = 10,
    tx_type: str = "all",
) -> Dict[str, Any]:
    limit = max(1, min(100, int(limit)))
    tx_type = (tx_type or "all").lower().strip()
    q = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    )
    rows = q.limit(limit * 3).all()
    filtered: List[Transaction] = []
    for tx in rows:
        t = (tx.type or "").lower()
        if tx_type == "debit" and t != "debit":
            continue
        if tx_type == "credit" and t != "credit":
            continue
        filtered.append(tx)
        if len(filtered) >= limit:
            break
    out: List[Dict[str, Any]] = []
    for tx in filtered:
        out.append(
            {
                "date": tx.date.strftime("%Y-%m-%d") if tx.date else None,
                "type": tx.type,
                "amount": round(float(tx.amount or 0.0), 2),
                "description": (tx.description or "")[:200],
                "category": tx.category or "Other",
            }
        )
    return {"ok": True, "count": len(out), "transactions": out}


def tool_search_knowledge(query: str, category: Optional[str], top_k: int = 5) -> Dict[str, Any]:
    top_k = max(1, min(15, int(top_k)))
    ret = retrieve_context(query or "", category=category, top_k=top_k)
    return {
        "ok": True,
        "grade": ret.get("grade"),
        "top_score": ret.get("top_score"),
        "hit_count": ret.get("hit_count"),
        "sources": ret.get("sources", []),
        "context": (ret.get("context") or "")[:12000],
        "category": category,
    }


def tool_get_user_context_snapshot(db: Session, user: User) -> Dict[str, Any]:
    ctx = build_user_context(db, user)
    return {
        "ok": True,
        "keys": ctx.get("keys", []),
        "prompt_text": ctx.get("prompt_text", ""),
        "generated_at": ctx.get("generated_at"),
    }


TOOL_REGISTRY: Dict[str, Any] = {
    "get_financial_summary": tool_get_financial_summary,
    "get_top_categories": tool_get_top_categories,
    "get_top_debit_transactions": tool_get_top_debit_transactions,
    "get_recent_transactions": tool_get_recent_transactions,
    "search_knowledge": tool_search_knowledge,
    "get_user_context_snapshot": tool_get_user_context_snapshot,
}


def execute_tool(
    name: str,
    db: Session,
    user: User,
    arguments: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    args = dict(arguments or {})
    fn = TOOL_REGISTRY.get(name)
    if not fn:
        return {"ok": False, "error": f"unknown_tool:{name}"}
    try:
        if name == "search_knowledge":
            return fn(
                query=str(args.get("query", "")),
                category=args.get("category"),
                top_k=int(args.get("top_k", 5)),
            )
        if name == "get_top_categories":
            return fn(db, user, limit=int(args.get("limit", 5)))
        if name == "get_top_debit_transactions":
            return fn(db, user, limit=int(args.get("limit", 5)))
        if name == "get_recent_transactions":
            return fn(
                db,
                user,
                limit=int(args.get("limit", 10)),
                tx_type=str(args.get("tx_type", "all")),
            )
        if name in ("get_financial_summary", "get_user_context_snapshot"):
            return fn(db, user)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:500]}
    return {"ok": False, "error": "tool_dispatch_failed"}


def infer_limit_from_message(message: str, default: int = 5) -> int:
    m = re.search(r"\b(?:top|first|last)\s+(\d{1,2})\b", message.lower())
    if m:
        return max(1, min(50, int(m.group(1))))
    return default


def default_tool_plan(route_agent: str, route_category: str, message: str) -> List[Dict[str, Any]]:
    """Heuristic plan when the LLM planner returns nothing usable."""
    lim = infer_limit_from_message(message, 5)
    if route_agent == "finance_agent":
        calls: List[Dict[str, Any]] = [
            {"name": "get_financial_summary", "arguments": {}},
            {"name": "get_user_context_snapshot", "arguments": {}},
        ]
        if any(k in message.lower() for k in ("top", "biggest", "highest", "largest", "debit")):
            calls.append({"name": "get_top_debit_transactions", "arguments": {"limit": lim}})
        if any(k in message.lower() for k in ("categor", "spend", "where", "budget")):
            calls.append({"name": "get_top_categories", "arguments": {"limit": lim}})
        return calls
    return [
        {"name": "get_user_context_snapshot", "arguments": {}},
        {
            "name": "search_knowledge",
            "arguments": {"query": message, "category": route_category, "top_k": 5},
        },
    ]

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from models import Card, Transaction, User
from services.financial_engine import canonical_year_month, transactions_in_month

from services.llm_service import call_llm, extract_json_object

from .agent_tools import get_card_data, get_credit_data, get_fraud_signals
from .prompts import (
    SUPERVISOR_ROUTER_PROMPT,
    WEALTH_AGENT_PROMPT,
    TELLER_AGENT_PROMPT,
    SCAM_AGENT_PROMPT,
    CLAIMS_AGENT_PROMPT,
    SYNTHESIZER_PROMPT,
)
from .state import AgentTraceEntry, AstraAgentState
from services.chat_tools import (
    tool_get_financial_summary,
    tool_get_recent_transactions,
)

logger = logging.getLogger(__name__)

VALID_AGENTS = {
    "wealth_agent",
    "teller_agent",
    "scam_agent",
    "claims_agent",
    "default_agent",
}

INSUFFICIENT_DATA = "I don't have enough data to answer this accurately."


def _format_inr(value: float) -> str:
    return f"₹{round(float(value), 2):,.2f}"


def _normalize_merchant_key(description: Optional[str]) -> str:
    line = (description or "").strip().split("\n")[0].strip()
    line = re.sub(r"\s+", " ", line)
    return line.lower()[:120] if line else "unknown"


def _compute_spending_metrics(db: Session, user: User) -> Dict[str, Any]:
    txs = (
        db.query(Transaction)
        .filter(Transaction.user_id == user.id)
        .order_by(Transaction.date.asc(), Transaction.id.asc())
        .all()
    )
    cy = canonical_year_month(txs)
    if not cy:
        return {
            "headline_month": None,
            "total_spend": 0.0,
            "category_totals": {},
            "top_category": None,
            "subscriptions": [],
        }
    year, month = cy
    month_txs = transactions_in_month(txs, year, month)
    debits = [tx for tx in month_txs if (tx.type or "").lower() == "debit"]
    category_totals: Dict[str, float] = defaultdict(float)
    merchant_counts: Dict[str, int] = defaultdict(int)
    merchant_amounts: Dict[str, float] = defaultdict(float)
    for tx in debits:
        amt = abs(float(tx.amount or 0.0))
        cat = (tx.category or "Other").strip() or "Other"
        category_totals[cat] += amt
        mkey = _normalize_merchant_key(tx.description)
        merchant_counts[mkey] += 1
        merchant_amounts[mkey] += amt
    total_spend = round(sum(category_totals.values()), 2)
    top_category = None
    if category_totals:
        top_category = max(category_totals.keys(), key=lambda c: category_totals[c])
    subscriptions: List[Dict[str, Any]] = []
    for mkey, count in merchant_counts.items():
        if count < 2:
            continue
        label = mkey if mkey != "unknown" else "Unknown merchant"
        subscriptions.append(
            {
                "merchant_key": mkey,
                "label": label[:80],
                "transactions": count,
                "total": round(merchant_amounts[mkey], 2),
            }
        )
    return {
        "headline_month": f"{year:04d}-{month:02d}",
        "total_spend": total_spend,
        "category_totals": category_totals,
        "top_category": top_category,
        "subscriptions": subscriptions,
    }


def _card_label(card: Card) -> str:
    return f"{card.bank_name} *{card.last4_digits}"


def _merchant_bucket(description: Optional[str]) -> Optional[str]:
    d = (description or "").lower()
    if "uber" in d: return "uber"
    if "swiggy" in d: return "swiggy"
    if "zomato" in d: return "zomato"
    if "amazon" in d or "amzn" in d: return "amazon"
    return None


def _is_hdfc(card: Card) -> bool:
    return "hdfc" in (card.bank_name or "").lower()


def _is_icici_amazon_card(card: Card) -> bool:
    b = (card.bank_name or "").lower()
    t = (card.card_type or "").lower()
    return "icici" in b and "amazon" in (t + b)


def _analyze_card_missed_savings(db: Session, user: User) -> Dict[str, Any]:
    cards = {c.id: c for c in db.query(Card).filter(Card.user_id == user.id).all()}
    txs = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    cy = canonical_year_month(txs)
    if not cy: return {"optimal": True, "suggestions": []}
    year, month = cy
    month_txs = transactions_in_month(txs, year, month)
    suggestions = []
    for tx in month_txs:
        if (tx.type or "").lower() != "debit" or not tx.card_id: continue
        card = cards.get(tx.card_id)
        if not card: continue
        amt = abs(float(tx.amount or 0.0))
        bucket = _merchant_bucket(tx.description)
        if bucket in ("swiggy", "zomato") and not _is_hdfc(card):
            suggestions.append({"merchant": bucket.title(), "better_card": "HDFC Swiggy (10%)", "savings": _format_inr(amt * 0.1)})
        elif bucket == "amazon" and not _is_icici_amazon_card(card):
            suggestions.append({"merchant": "Amazon", "better_card": "ICICI Amazon (5%)", "savings": _format_inr(amt * 0.05)})
    return {"optimal": len(suggestions) == 0, "suggestions": suggestions[:3]}


def _append_trace(state: AstraAgentState, entry: AgentTraceEntry) -> List[AgentTraceEntry]:
    # Parallel nodes will have their traces merged by the operator.add reducer
    return [entry]


def _build_unified_context(
    user_query: str,
    data: Dict[str, Any],
    computed_metrics: Dict[str, Any],
    insights: Dict[str, Any],
    derived: Dict[str, Any] = None,
) -> Dict[str, Any]:
    return {
        "user_query": user_query.strip(),
        "data": data,
        "computed_metrics": computed_metrics,
        "insights": insights,
        "derived": derived or {},
    }


def _compute_derived_signals(db: Session, user: User) -> Dict[str, Any]:
    credit_data = get_credit_data(db, user)
    spending_metrics = _compute_spending_metrics(db, user)
    txs = db.query(Transaction).filter(Transaction.user_id == user.id).all()
    insurance_keywords = ["lic", "insurance", "premium", "policy", "mediclaim", "hdfc ergo", "tata aig"]
    detected_insurance_txs = []
    for tx in txs:
        desc = (tx.description or "").lower()
        if any(kw in desc for kw in insurance_keywords):
            detected_insurance_txs.append({"date": str(tx.date), "desc": tx.description, "amount": float(tx.amount or 0)})
    return {
        "credit_utilization": credit_data.get("credit_utilization_pct"),
        "has_low_cibil": (credit_data.get("credit_score") or 900) < 700,
        "detected_insurance_patterns": detected_insurance_txs,
        "is_insured": len(detected_insurance_txs) > 0,
        "total_spend_month": spending_metrics.get("total_spend"),
        "top_category": spending_metrics.get("top_category"),
    }


def _render_prompt(template: str, user_message: str, input_json: Dict[str, Any]) -> str:
    return (
        template.replace("{{USER_MESSAGE}}", user_message.strip())
        .replace("{{INPUT_JSON}}", json.dumps(input_json, indent=2, ensure_ascii=False))
    )


def supervisor_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    message = state.get("message", "").lower()
    agents = set()
    if any(kw in message for kw in ["insurance", "policy", "premium", "lic", "claim"]):
        agents.add("claims_agent")
    if any(kw in message for kw in ["cibil", "credit", "score", "loan", "card"]):
        agents.add("wealth_agent")
    if any(kw in message for kw in ["balance", "account", "transaction", "statement", "spent"]):
        agents.add("teller_agent")
    if any(kw in message for kw in ["fraud", "scam", "suspicious", "otp"]):
        agents.add("scam_agent")

    prompt = _render_prompt(SUPERVISOR_ROUTER_PROMPT, state.get("message", ""), {})
    try:
        raw = call_llm(prompt, temperature=0.0)
        parsed = extract_json_object(raw) or {}
        for a in (parsed.get("agents") or []):
            name = a.lower() if a else ""
            if name in VALID_AGENTS: agents.add(name)
    except Exception: pass

    if not agents:
        agents.add("default_agent")
    agents_to_run = list(agents)
    logger.info("supervisor.agents_to_run=%s user_id=%s", agents_to_run, getattr(user, "id", None))
    derived = _compute_derived_signals(db, user)

    return {
        "agents_to_run": agents_to_run,
        "agent_trace": _append_trace(state, {"step": "supervisor", "agent": "supervisor", "detail": f"parallel_intents: {agents_to_run}"}),
        "derived_data": derived,
        "agent_responses": {}, 
    }


def wealth_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node wealth_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    derived = state.get("derived_data") or {}
    payload = {
        "credit": get_credit_data(db, user),
        "spending": _compute_spending_metrics(db, user),
        "cards": {**get_card_data(db, user), "missed_savings": _analyze_card_missed_savings(db, user)}
    }
    prompt = _render_prompt(WEALTH_AGENT_PROMPT, user_message, {"payload": payload, "derived": derived})
    raw = call_llm(prompt)
    structured = extract_json_object(raw) or {"answer": raw, "confidence": 0.7}
    return {
        "agent_responses": {"wealth_agent": structured},
        "agent_trace": _append_trace(state, {"step": "wealth_agent", "agent": "wealth_agent", "detail": "parallel_wealth_analysis"})
    }


def teller_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node teller_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    payload = {"summary": tool_get_financial_summary(db, user), "recent": tool_get_recent_transactions(db, user, 10)}
    prompt = _render_prompt(TELLER_AGENT_PROMPT, user_message, payload)
    raw = call_llm(prompt)
    structured = extract_json_object(raw) or {"answer": raw, "confidence": 0.9}
    return {
        "agent_responses": {"teller_agent": structured},
        "agent_trace": _append_trace(state, {"step": "teller_agent", "agent": "teller_agent", "detail": "parallel_teller_analysis"})
    }


def claims_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node claims_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    derived = state.get("derived_data") or {}
    prompt = _render_prompt(CLAIMS_AGENT_PROMPT, user_message, {"derived": derived})
    raw = call_llm(prompt)
    structured = extract_json_object(raw) or {"answer": raw, "confidence": 0.6}
    return {
        "agent_responses": {"claims_agent": structured},
        "agent_trace": _append_trace(state, {"step": "claims_agent", "agent": "claims_agent", "detail": "parallel_claims_analysis"})
    }


def scam_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node scam_agent user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    prompt = _render_prompt(SCAM_AGENT_PROMPT, user_message, {"signals": get_fraud_signals(db, user, user_message)})
    raw = call_llm(prompt)
    structured = extract_json_object(raw) or {"answer": raw, "confidence": 0.8}
    return {
        "agent_responses": {"scam_agent": structured},
        "agent_trace": _append_trace(state, {"step": "scam_agent", "agent": "scam_agent", "detail": "parallel_scam_analysis"})
    }


def synthesizer_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node synthesizer user_id=%s", getattr(user, "id", None))
    user_message = state.get("message", "")
    responses = state.get("agent_responses") or {}
    responses_str = ""
    for agent, data in responses.items():
        ans = data.get("answer") if isinstance(data, dict) else data
        conf = data.get("confidence", 0.5) if isinstance(data, dict) else 0.5
        responses_str += f"### {agent.upper()} (Confidence: {conf})\n{ans}\n\n"
        
    prompt = SYNTHESIZER_PROMPT.replace("{{USER_MESSAGE}}", user_message).replace("{{AGENT_RESPONSES}}", responses_str)
    final_answer = call_llm(prompt)

    return {
        "final_answer": final_answer,
        "agent_trace": _append_trace(state, {"step": "synthesizer", "agent": "supervisor", "detail": "logical_parallel_synthesis"})
    }


def default_node(state: AstraAgentState, db: Session, user: User) -> AstraAgentState:
    logger.info("multi_agent.node default_agent user_id=%s", getattr(user, "id", None))
    return {
        "final_answer": "I'm sorry, I couldn't find a specialized agent to handle your request. Could you please clarify your financial question?",
        "agent_trace": _append_trace(state, {"step": "default_agent", "agent": "default_agent", "detail": "unsupported_query"})
    }

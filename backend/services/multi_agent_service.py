from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from agents.multi_agent.graph import run_multi_agent_chat
from models import User
from services.agent_router import AgentRoute
from services.chat_policy import build_response_envelope

logger = logging.getLogger(__name__)

INSUFFICIENT_DATA = "I don't have enough data to answer this accurately."


def _as_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _subscription_names(subs: Any) -> List[str]:
    names: List[str] = []
    if not isinstance(subs, list):
        return names
    for raw in subs:
        if not isinstance(raw, str):
            continue
        name = raw.split("(")[0].strip()
        if name:
            names.append(name.title())
    return names


def _render_spending(structured: Dict[str, Any]) -> str:
    insights = _as_list(structured.get("insights"))
    if not insights or (len(insights) == 1 and insights[0] == INSUFFICIENT_DATA):
        if str(structured.get("summary") or "").strip() == INSUFFICIENT_DATA:
            return INSUFFICIENT_DATA
    subs = structured.get("subscriptions_detected")
    if subs is None:
        subs = structured.get("subscriptions")
    names = _subscription_names(subs if isinstance(subs, list) else [])
    n_sub = len(subs) if isinstance(subs, list) else 0
    sub_note = ""
    if n_sub >= 3 and names:
        sub_note = f" You also have {n_sub} recurring subscriptions including {', '.join(names[:3])}."
    elif n_sub > 0 and names:
        sub_note = f" Recurring merchants include {', '.join(names)}."

    if insights and insights[0] != INSUFFICIENT_DATA:
        body = " ".join(insights).strip()
        if sub_note:
            body = (body + sub_note).strip()
        return body or INSUFFICIENT_DATA

    summary = str(structured.get("summary") or "").strip()
    if summary and summary != INSUFFICIENT_DATA:
        return (summary + sub_note).strip() or INSUFFICIENT_DATA
    return INSUFFICIENT_DATA


def _render_credit(structured: Dict[str, Any]) -> str:
    lines = [f"**Score analysis:** {structured.get('score_analysis', INSUFFICIENT_DATA)}"]
    risk_factors = _as_list(structured.get("risk_factors"))
    if risk_factors:
        lines.append("**Risk factors:**")
        lines.extend(f"- {item}" for item in risk_factors)
    positives = _as_list(structured.get("positive_factors"))
    if positives:
        lines.append("**Positive factors:**")
        lines.extend(f"- {item}" for item in positives)
    actions = _as_list(structured.get("improvement_actions"))
    if actions:
        lines.append("**Improvement actions:**")
        lines.extend(f"- {item}" for item in actions)
    lines.append(f"**Predicted impact:** {structured.get('predicted_impact', INSUFFICIENT_DATA)}")
    return "\n".join(lines)


def _card_example_line(s0: Dict[str, Any]) -> str:
    m = str(s0.get("merchant", "that merchant"))
    bc = (s0.get("better_card") or "").lower()
    if "hdfc" in bc or "10%" in bc or "food" in bc:
        return f"For example, {m} payments should use HDFC for 10% cashback."
    if "icici" in bc and "amazon" in bc:
        return f"For example, {m} payments should use your ICICI Amazon card for 5% cashback."
    return (
        f"For example, route {m} spend through {s0.get('better_card', 'a better-matched card')} "
        f"instead of {s0.get('used_card', 'the card you used')}."
    )


def _render_card(structured: Dict[str, Any]) -> str:
    if str(structured.get("card_usage_summary") or "").strip() == INSUFFICIENT_DATA:
        return INSUFFICIENT_DATA
    impact = str(structured.get("impact") or "").strip()
    usage = str(structured.get("card_usage_summary") or "").strip()
    missed = structured.get("missed_savings_total", structured.get("missed_savings", ""))
    parts: List[str] = []
    if impact:
        line = impact.rstrip(".")
        if "optimizing" not in line.lower() and "no missed" not in line.lower():
            line += " by optimizing card usage"
        parts.append(line + ".")
    elif missed:
        parts.append(
            f"You could have saved {missed} this month by optimizing card usage."
        )
    if usage and "optimal usage detected" not in usage.lower():
        parts.append(usage)
    suggestions = structured.get("suggestions") or structured.get("better_card_suggestions") or []
    if suggestions:
        parts.append(_card_example_line(suggestions[0]))
        if len(suggestions) > 1:
            parts.append(f"There are {len(suggestions)} such opportunities in your data this month.")
    text = " ".join(p for p in parts if p).strip()
    return text or INSUFFICIENT_DATA


def _render_fraud(structured: Dict[str, Any]) -> str:
    risk = str(structured.get("risk_level") or "MEDIUM").upper()
    if str(structured.get("reason") or "").strip() == INSUFFICIENT_DATA:
        return INSUFFICIENT_DATA
    conf = str(structured.get("confidence") or "").strip()
    urgency = str(structured.get("urgency") or "").strip()
    reason = str(structured.get("reason") or "").strip()
    action = str(structured.get("recommended_action") or "").strip()
    lead = f"This looks like a {risk} risk transaction"
    if conf:
        lead += f" ({conf} confidence)"
    lead += "."
    if urgency:
        u = urgency.strip()
        if not u.endswith("."):
            u += "."
        lead += f" {u}"
    parts: List[str] = [lead]
    mid = reason
    if structured.get("matches_banking_scam_patterns") and "scam pattern" not in mid.lower():
        mid += " This matches known banking scam patterns."
    parts.append(mid)
    if action:
        parts.append(action)
    combined = " ".join(p for p in parts if p).strip()
    if risk == "HIGH" and "do not proceed" not in combined.lower():
        combined += " Do not proceed with this transaction."
    return combined.strip()


def _render_structured_response(agent_used: str, structured: Dict[str, Any]) -> str:
    if agent_used == "spending_agent":
        return _render_spending(structured)
    if agent_used == "credit_agent":
        return _render_credit(structured)
    if agent_used == "card_agent":
        return _render_card(structured)
    if agent_used == "fraud_agent":
        return _render_fraud(structured)
    return INSUFFICIENT_DATA


def run_multi_agent_service(
    db: Session,
    user: User,
    message: str,
    memory: Optional[List[Dict[str, Any]]] = None,
    route: Optional[AgentRoute] = None,
    agent_hint: Optional[str] = None,
) -> Dict[str, Any]:
    try:
        state = run_multi_agent_chat(
            db=db,
            user=user,
            message=message,
            memory=memory,
            route=route,
            agent_hint=agent_hint,
        )
    except Exception as exc:
        logger.exception("multi_agent graph failed: %s", exc)
        return build_response_envelope(
            type_name="default_agent",
            response=INSUFFICIENT_DATA,
            sources=[],
            reason="multi_agent_safe_fallback",
            confidence=0.2,
            route=route,
            data={
                "agentic": True,
                "agent_used": "default_agent",
                "agent_trace": [],
                "structured_output": {},
                "tool_results": {},
                "explanation": "Safe fallback after an internal error.",
            },
        )

    agent_used = str(state.get("next_agent") or "default_agent")
    structured_output = dict(state.get("structured_output") or {})
    response_text = str(state.get("final_answer") or "").strip()
    if not response_text:
        response_text = _render_structured_response(agent_used, structured_output)

    logger.info(
        "multi_agent.response agent=%s sources=%s trace_steps=%s",
        agent_used,
        state.get("sources", []),
        len(state.get("agent_trace", [])),
    )

    return build_response_envelope(
        type_name=agent_used,
        response=response_text,
        sources=list(state.get("sources") or ["db"]),
        reason=str(state.get("reason") or "multi_agent"),
        confidence=float(state.get("confidence") or 0.0),
        route=route,
        data={
            "agentic": True,
            "agent_used": agent_used,
            "agent_trace": state.get("agent_trace", []),
            "structured_output": structured_output,
            "tool_results": state.get("tool_results", {}),
            "final_answer": response_text,
            "explanation": "Response produced by the LangGraph multi-agent pipeline.",
        },
    )

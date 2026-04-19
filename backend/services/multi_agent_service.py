from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from agents.multi_agent.graph import run_multi_agent_chat
from models import User
from services.agent_router import AgentRoute
from services.chat_policy import build_response_envelope

logger = logging.getLogger(__name__)

INSUFFICIENT_DATA = "I don't have enough data to answer this accurately."


def _expose_multi_agent_errors() -> bool:
    return os.getenv("AGENTIC_DEBUG", "").lower() in ("1", "true", "yes")


def run_multi_agent_service(
    db: Session,
    user: User,
    message: str,
    memory: Optional[List[Dict[str, Any]]] = None,
    route: Optional[AgentRoute] = None,
    agent_hint: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Executes the Multi-Agent LangGraph pipeline and returns a normalized response.
    The new pipeline uses a Multi-Intent Simulator and a Synthesizer.
    """
    try:
        state = run_multi_agent_chat(
            db=db,
            user=user,
            message=message,
            memory=memory,
            agent_hint=agent_hint,
        )
    except Exception as exc:
        logger.exception("multi_agent graph failed: %s", exc)
        detail = f"{type(exc).__name__}: {exc}"
        user_text = (
            f"[multi-agent error] {detail}" if _expose_multi_agent_errors() else INSUFFICIENT_DATA
        )
        return build_response_envelope(
            type_name="error" if _expose_multi_agent_errors() else "default_agent",
            response=user_text[:2000],
            sources=[],
            reason="multi_agent_safe_fallback",
            confidence=0.2,
            route=route,
            data={
                "agentic": True,
                "agent_used": "error" if _expose_multi_agent_errors() else "default_agent",
                "agent_trace": [],
                "structured_output": {},
                "tool_results": {},
                "explanation": "Safe fallback after an internal error.",
                "error_class": type(exc).__name__,
                "error_message": str(exc)[:2000],
            },
        )

    # In the new architecture, the synthesizer produces the final answer.
    response_text = str(state.get("final_answer") or "").strip()
    if not response_text:
        response_text = INSUFFICIENT_DATA

    # We can list all agents that were run for the UI trace
    agents_run = state.get("agents_to_run") or []
    primary_agent = agents_run[0] if agents_run else "default_agent"

    logger.info(
        "multi_agent.response agents=%s sources=%s trace_steps=%s",
        agents_run,
        state.get("sources", []),
        len(state.get("agent_trace", [])),
    )

    return build_response_envelope(
        type_name=primary_agent,
        response=response_text,
        sources=list(state.get("sources") or ["db"]),
        reason=str(state.get("reason") or "multi_agent_synthesis"),
        confidence=float(state.get("confidence") or 0.85),
        route=route,
        data={
            "agentic": True,
            "agents_run": agents_run,
            "agent_trace": state.get("agent_trace", []),
            "derived_data": state.get("derived_data", {}),
            "agent_responses": state.get("agent_responses", {}),
            "final_answer": response_text,
            "explanation": "Holistic response synthesized from multiple specialized agents.",
        },
    )

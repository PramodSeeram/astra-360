"""Chat orchestration.

Default path: **agentic** planner → tools → synthesizer (LLM decides tools).

Legacy path (``USE_AGENTIC_CHAT=false``): deterministic finance templates
or RAG + knowledge agents without a planner.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models import User
from services.agent_loop import USE_AGENTIC_CHAT, run_agentic_chat
from services.agent_router import AgentRoute, route_query
from services.chat_policy import (
    build_response_envelope,
    finance_snapshot_data,
    finance_sources,
)
from services.financial_engine import build_financial_snapshot, render_finance_answer
from services.knowledge_agents import answer_with_knowledge
from services.knowledge_base_service import retrieve_context
from services.user_context_service import build_user_context

logger = logging.getLogger(__name__)


def build_chat_response(
    db: Session,
    user: User,
    message: str,
    memory: Optional[List[Dict[str, Any]]] = None,
    route: Optional[AgentRoute] = None,
) -> Dict[str, Any]:
    """Produce a normalized chat payload for the UI."""

    if route is None:
        route = route_query(message)

    memory = memory or []

    if USE_AGENTIC_CHAT:
        try:
            return run_agentic_chat(db, user, message, memory, route)
        except Exception as exc:
            logger.exception("agentic chat failed, falling back to legacy: %s", exc)

    return _build_legacy_chat_response(db, user, message, memory, route)


def _build_legacy_chat_response(
    db: Session,
    user: User,
    message: str,
    memory: List[Dict[str, Any]],
    route: AgentRoute,
) -> Dict[str, Any]:
    if route.agent == "finance_agent":
        snapshot = build_financial_snapshot(db, user)
        rendered = render_finance_answer(message, snapshot)

        return build_response_envelope(
            type_name=route.agent,
            response=rendered,
            sources=finance_sources(snapshot),
            reason="finance_db_snapshot" if snapshot.transactions_found else "finance_no_data",
            confidence=0.95 if snapshot.transactions_found else 0.4,
            route=route,
            data=finance_snapshot_data(snapshot),
        )

    user_context = build_user_context(db, user)
    retrieval = retrieve_context(message, category=route.category, top_k=5)

    answer = answer_with_knowledge(
        agent_name=route.agent,
        user_query=message,
        retrieval=retrieval,
        memory=memory,
        user_context=user_context,
    )

    envelope = build_response_envelope(
        type_name=route.agent,
        response=answer["response"],
        sources=answer.get("sources", []),
        reason=answer.get("reason", "rag_answer"),
        confidence=answer.get("confidence", 0.0),
        route=route,
        data={
            "category": route.category,
            "top_score": retrieval.get("top_score", 0.0),
            "hit_count": retrieval.get("hit_count", 0),
            "matches": retrieval.get("results", []),
            "user_context_keys": user_context.get("keys", []),
            "agentic": False,
        },
    )
    if answer.get("ui_action"):
        envelope["ui_action"] = answer["ui_action"]
    if answer.get("actions"):
        envelope["actions"] = answer["actions"]
    return envelope

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models import User
from services.agent_router import AgentRoute

from .nodes import (
    card_node,
    credit_node,
    default_node,
    fraud_node,
    spending_node,
    supervisor_node,
)
from .state import AstraAgentState

from langgraph.graph import END, StateGraph


def _serialize_route(route: Optional[AgentRoute]) -> Dict[str, Any]:
    if route is None:
        return {}
    return {
        "agent": route.agent,
        "category": route.category,
        "confidence": route.confidence,
        "reason": route.reason,
        "keywords_matched": list(route.keywords_matched),
    }


def build_multi_agent_graph(db: Session, user: User):
    workflow = StateGraph(AstraAgentState)

    workflow.add_node("supervisor", lambda state: supervisor_node(state, db, user))
    workflow.add_node("spending_agent", lambda state: spending_node(state, db, user))
    workflow.add_node("credit_agent", lambda state: credit_node(state, db, user))
    workflow.add_node("card_agent", lambda state: card_node(state, db, user))
    workflow.add_node("fraud_agent", lambda state: fraud_node(state, db, user))
    workflow.add_node("default_agent", lambda state: default_node(state, db, user))

    workflow.set_entry_point("supervisor")
    workflow.add_conditional_edges(
        "supervisor",
        lambda state: state.get("next_agent", "default_agent"),
        {
            "spending_agent": "spending_agent",
            "credit_agent": "credit_agent",
            "card_agent": "card_agent",
            "fraud_agent": "fraud_agent",
            "default_agent": "default_agent",
        },
    )

    for node_name in (
        "spending_agent",
        "credit_agent",
        "card_agent",
        "fraud_agent",
        "default_agent",
    ):
        workflow.add_edge(node_name, END)

    return workflow.compile()


def run_multi_agent_chat(
    db: Session,
    user: User,
    message: str,
    memory: Optional[List[Dict[str, Any]]] = None,
    route: Optional[AgentRoute] = None,
    agent_hint: Optional[str] = None,
) -> AstraAgentState:
    app = build_multi_agent_graph(db, user)
    initial_state: AstraAgentState = {
        "messages": list(memory or []),
        "message": message,
        "user_id": user.id,
        "agent_hint": agent_hint,
        "route_hint": _serialize_route(route),
        "agent_trace": [],
    }
    return app.invoke(initial_state)

from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models import User

from database import SessionLocal
from .nodes import (
    supervisor_node,
    spending_node,
    budget_node,
    wealth_node,
    teller_node,
    claims_node,
    scam_node,
    billing_node,
    synthesizer_node,
    default_node,
)
from .state import AstraAgentState

from langgraph.graph import END, StateGraph
from langgraph.types import Send

# Nodes that participate in parallel fan-out (must match add_conditional_edges map).
_PARALLEL_AGENT_NODES = frozenset(
    {"spending_agent", "budget_agent", "wealth_agent", "teller_agent", "claims_agent", "scam_agent", "billing_agent"},
)


def build_multi_agent_graph(db: Session, user: User):
    workflow = StateGraph(AstraAgentState)

    def _get_node_wrapper(node_func):
        def wrapper(state: AstraAgentState):
            user_id = state.get("user_id")
            with SessionLocal() as db_session:
                user_obj = db_session.query(User).filter(User.id == user_id).first()
                if not user_obj:
                    # Fallback or error
                    return node_func(state, db_session, user) # Use original user as fallback
                return node_func(state, db_session, user_obj)
        return wrapper

    # Add Nodes
    workflow.add_node("supervisor", _get_node_wrapper(supervisor_node))
    workflow.add_node("spending_agent", _get_node_wrapper(spending_node))
    workflow.add_node("budget_agent", _get_node_wrapper(budget_node))
    workflow.add_node("wealth_agent", _get_node_wrapper(wealth_node))
    workflow.add_node("teller_agent", _get_node_wrapper(teller_node))
    workflow.add_node("claims_agent", _get_node_wrapper(claims_node))
    workflow.add_node("scam_agent", _get_node_wrapper(scam_node))
    workflow.add_node("billing_agent", _get_node_wrapper(billing_node))
    workflow.add_node("synthesizer", _get_node_wrapper(synthesizer_node))
    workflow.add_node("default_agent", _get_node_wrapper(default_node))

    # Entry Point
    workflow.set_entry_point("supervisor")

    # 🚀 PARALLEL FAN-OUT 
    # The router returns a list of nodes to execute in parallel.
    def route_supervisor(state: AstraAgentState):
        agents = list(state.get("agents_to_run") or [])
        if not agents:
            return "default_agent"
        if "default_agent" in agents:
            return "default_agent"
        specialized = [a for a in agents if a in _PARALLEL_AGENT_NODES]
        if not specialized:
            return "default_agent"
        # LangGraph 0.6+: parallel branches require Send(...); a bare list of strings is unreliable.
        if len(specialized) == 1:
            return specialized[0]
        return [Send(name, state) for name in specialized]

    workflow.add_conditional_edges(
        "supervisor",
        route_supervisor,
        {
            "spending_agent": "spending_agent",
            "budget_agent": "budget_agent",
            "wealth_agent": "wealth_agent",
            "teller_agent": "teller_agent",
            "claims_agent": "claims_agent",
            "scam_agent": "scam_agent",
            "billing_agent": "billing_agent",
            "default_agent": "default_agent",
        }
    )

    # 🚀 FAN-IN / AGGREGATION
    # All parallel agent paths converge here automatically
    workflow.add_edge("spending_agent", "synthesizer")
    workflow.add_edge("budget_agent", "synthesizer")
    workflow.add_edge("wealth_agent", "synthesizer")
    workflow.add_edge("teller_agent", "synthesizer")
    workflow.add_edge("claims_agent", "synthesizer")
    workflow.add_edge("scam_agent", "synthesizer")
    workflow.add_edge("billing_agent", "synthesizer")

    # Final Step
    workflow.add_edge("synthesizer", END)
    workflow.add_edge("default_agent", END)

    return workflow.compile()


def run_multi_agent_chat(
    db: Session,
    user: User,
    message: str,
    memory: Optional[List[Dict[str, Any]]] = None,
    agent_hint: Optional[str] = None,
) -> AstraAgentState:
    app = build_multi_agent_graph(db, user)
    initial_state: AstraAgentState = {
        "messages": list(memory or []),
        "message": message,
        "user_id": user.id,
        "agent_hint": agent_hint,
        "agent_trace": [],
        "agent_responses": {},
        "agents_to_run": [],
    }
    return app.invoke(initial_state)

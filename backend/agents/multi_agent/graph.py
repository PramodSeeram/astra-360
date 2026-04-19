from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from models import User

from .nodes import (
    supervisor_node,
    wealth_node,
    teller_node,
    claims_node,
    scam_node,
    synthesizer_node,
    default_node,
)
from .state import AstraAgentState

from langgraph.graph import END, StateGraph
from langgraph.types import Send

# Nodes that participate in parallel fan-out (must match add_conditional_edges map).
_PARALLEL_AGENT_NODES = frozenset(
    {"wealth_agent", "teller_agent", "claims_agent", "scam_agent"},
)


def build_multi_agent_graph(db: Session, user: User):
    workflow = StateGraph(AstraAgentState)

    # Add Nodes
    workflow.add_node("supervisor", lambda state: supervisor_node(state, db, user))
    workflow.add_node("wealth_agent", lambda state: wealth_node(state, db, user))
    workflow.add_node("teller_agent", lambda state: teller_node(state, db, user))
    workflow.add_node("claims_agent", lambda state: claims_node(state, db, user))
    workflow.add_node("scam_agent", lambda state: scam_node(state, db, user))
    workflow.add_node("synthesizer", lambda state: synthesizer_node(state, db, user))
    workflow.add_node("default_agent", lambda state: default_node(state, db, user))

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
            "wealth_agent": "wealth_agent",
            "teller_agent": "teller_agent",
            "claims_agent": "claims_agent",
            "scam_agent": "scam_agent",
            "default_agent": "default_agent",
        }
    )

    # 🚀 FAN-IN / AGGREGATION
    # All parallel agent paths converge here automatically
    workflow.add_edge("wealth_agent", "synthesizer")
    workflow.add_edge("teller_agent", "synthesizer")
    workflow.add_edge("claims_agent", "synthesizer")
    workflow.add_edge("scam_agent", "synthesizer")

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

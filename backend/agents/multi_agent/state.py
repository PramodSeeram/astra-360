from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict


class AgentTraceEntry(TypedDict, total=False):
    step: str
    agent: str
    tool: str
    reason: str
    detail: str
    duration_ms: int
    tools_used: List[str]
    key_metrics: Dict[str, Any]


def merge_dicts(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Reducer to merge dictionaries during parallel LangGraph execution."""
    return {**a, **b}


class AstraAgentState(TypedDict, total=False):
    messages: List[Dict[str, Any]]
    message: str
    user_id: int
    agent_hint: Optional[str]
    route_hint: Dict[str, Any]
    next_agent: str
    agents_to_run: List[str]
    # Reducers are required for keys that multiple parallel nodes write to
    agent_responses: Annotated[Dict[str, Any], merge_dicts]
    agent_trace: Annotated[List[AgentTraceEntry], operator.add]
    derived_data: Dict[str, Any]
    tool_results: Dict[str, Any]
    structured_output: Dict[str, Any]
    sources: List[str]
    confidence: float
    reason: str
    final_answer: str
    unified_context: Dict[str, Any]
    legacy_result: Dict[str, Any]

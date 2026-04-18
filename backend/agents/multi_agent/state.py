from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class AgentTraceEntry(TypedDict, total=False):
    step: str
    agent: str
    tool: str
    reason: str
    detail: str
    duration_ms: int
    tools_used: List[str]
    key_metrics: Dict[str, Any]


class AstraAgentState(TypedDict, total=False):
    messages: List[Dict[str, Any]]
    message: str
    user_id: int
    agent_hint: Optional[str]
    route_hint: Dict[str, Any]
    next_agent: str
    tool_results: Dict[str, Any]
    structured_output: Dict[str, Any]
    sources: List[str]
    confidence: float
    reason: str
    agent_trace: List[AgentTraceEntry]
    final_answer: str
    unified_context: Dict[str, Any]
    legacy_result: Dict[str, Any]

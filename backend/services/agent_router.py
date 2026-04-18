"""Single source of truth for chat intent routing.

The router is called exactly once per request in ``chat_routes`` and the
resulting ``AgentRoute`` is threaded down to ``chat_service`` so we never
re-route mid-pipeline (which was previously causing divergent behavior
between the activation gate and the answering layer).
"""

from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class AgentRoute:
    agent: str
    category: str
    confidence: float = 0.0
    reason: str = "default_finance"
    keywords_matched: Tuple[str, ...] = field(default_factory=tuple)


_ROUTING_TABLE: List[Tuple[str, str, Tuple[str, ...]]] = [
    (
        "scam_agent",
        "scam",
        ("scam", "fraud", "otp", "phishing", "fake call", "upi fraud"),
    ),
    (
        "insurance_agent",
        "insurance",
        ("insurance", "policy", "premium", "claim", "sum assured", "mediclaim"),
    ),
    (
        "tax_agent",
        "tax",
        ("tax", "itr", "gst", "80c", "tds", "deduction", "regime"),
    ),
]


def route_query(query: str) -> AgentRoute:
    text = (query or "").lower().strip()
    if not text:
        return AgentRoute(
            agent="finance_agent",
            category="finance",
            confidence=0.3,
            reason="empty_query_default",
        )

    best_match: Tuple[str, str, Tuple[str, ...]] | None = None
    for agent, category, keywords in _ROUTING_TABLE:
        hits = tuple(kw for kw in keywords if kw in text)
        if hits:
            best_match = (agent, category, hits)
            break

    if best_match is not None:
        agent, category, hits = best_match
        return AgentRoute(
            agent=agent,
            category=category,
            confidence=0.9 if len(hits) > 1 else 0.75,
            reason="keyword_match",
            keywords_matched=hits,
        )

    return AgentRoute(
        agent="finance_agent",
        category="finance",
        confidence=0.6,
        reason="default_finance",
    )

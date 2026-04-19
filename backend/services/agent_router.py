"""Single source of truth for chat intent routing.

The router is called exactly once per request in ``chat_routes`` and the
resulting ``AgentRoute`` is threaded down to ``chat_service`` so we never
re-route mid-pipeline.
"""

import re
from dataclasses import dataclass, field
from typing import List, Tuple


@dataclass(frozen=True)
class AgentRoute:
    agent: str
    category: str
    confidence: float = 0.0
    reason: str = "default_finance"
    keywords_matched: Tuple[str, ...] = field(default_factory=tuple)


# Updated to match the new Multi-Agent Digital Brain structure
_ROUTING_TABLE: List[Tuple[str, str, Tuple[str, ...]]] = [
    (
        "scam_agent",
        "scam",
        ("scam", "fraud", "otp", "phishing", "fake call", "upi fraud", "suspicious"),
    ),
    (
        "claims_agent",
        "insurance",
        ("insurance", "policy", "premium", "claim", "sum assured", "mediclaim", "lic", "hdfc ergo"),
    ),
    (
        "spending_agent",
        "spending",
        (
            "spend",
            "spent",
            "expense",
            "expenses",
            "swiggy",
            "zomato",
            "food",
            "where did i spend",
            "breakdown",
            "analysis",
        ),
    ),
    (
        "budget_agent",
        "budget",
        (
            "budget",
            "income",
            "salary",
            "payroll",
            "savings",
            "save money",
            "how much do i save",
            "plan my budget",
        ),
    ),
    (
        "wealth_agent",
        "wealth",
        (
            "wealth",
            "invest",
            "portfolio",
            "cibil",
            "loan",
            "credit card",
            "best credit card",
            "which credit card",
            "card benefit",
            "best card",
            "which card",
        ),
    ),
    (
        "teller_agent",
        "banking",
        (
            "teller",
            "balance",
            "account",
            "transaction",
            "statement",
            "debit",
            "credit limit",
            "how much money do i have",
            "current balance",
            "my balance",
        ),
    ),
]


def _route_money_query(text: str) -> AgentRoute | None:
    bank_compare_tokens = ("sbi", "federal", "hdfc", "icici", "axis", "kotak", "amex")
    if any(token in text for token in bank_compare_tokens) and any(
        token in text for token in (" or ", " vs ", "versus", "better", "best", "which")
    ):
        return AgentRoute(
            agent="wealth_agent",
            category="wealth",
            confidence=0.9,
            reason="bank_card_comparison_query",
        )
    if "insurance" in text or "policy" in text:
        return AgentRoute(
            agent="claims_agent",
            category="insurance",
            confidence=0.9,
            reason="keyword_match",
            keywords_matched=("insurance",) if "insurance" in text else ("policy",),
        )
    if (
        "credit card" in text
        or "best credit card" in text
        or "which credit card" in text
        or "card benefit" in text
        or ("best" in text and "card" in text)
    ):
        return AgentRoute(
            agent="wealth_agent",
            category="wealth",
            confidence=0.9,
            reason="card_choice_query",
        )
    if any(phrase in text for phrase in ("where is my money going", "money going", "outflow", "cash flow")):
        return AgentRoute(
            agent="spending_agent",
            category="spending",
            confidence=0.9,
            reason="cashflow_spend_query",
        )
    if (
        "how much money" in text and "do i have" in text
    ) or "current balance" in text or "my balance" in text:
        return AgentRoute(
            agent="teller_agent",
            category="banking",
            confidence=0.9,
            reason="balance_query",
        )
    if re.search(r"\bsaving\b", text) or re.search(r"\bsave\b", text):
        return AgentRoute(
            agent="budget_agent",
            category="budget",
            confidence=0.8,
            reason="budget_query",
        )
    return None


def route_query(query: str) -> AgentRoute:
    text = (query or "").lower().strip()
    if not text:
        return AgentRoute(
            agent="wealth_agent",
            category="wealth",
            confidence=0.3,
            reason="empty_query_default",
        )

    routed = _route_money_query(text)
    if routed is not None:
        return routed

    best_match: Tuple[str, str, Tuple[str, ...]] | None = None
    for agent, category, keywords in _ROUTING_TABLE:
        hits = tuple(kw for kw in keywords if kw in text)
        if hits:
            # For the demo, if multiple match, we take the first or specifically look for insurance/claims
            if "insurance" in text or "policy" in text:
                best_match = ("claims_agent", "insurance", hits)
                break
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
        agent="wealth_agent",
        category="wealth",
        confidence=0.6,
        reason="default_finance",
    )

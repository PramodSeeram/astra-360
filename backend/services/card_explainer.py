"""
Card Explainer — LLM-powered explanation layer.

The LLM here has ONE job: expand the base reasoning into a professional,
concise explanation.  It is FORBIDDEN from changing the card name or
overriding the decision made by the rule engine.

If the LLM call fails for any reason the base_reason is returned as-is,
ensuring the system degrades gracefully without losing the correct answer.
"""

from __future__ import annotations

import logging

from services.decision_engine import CardDecision
from services.llm_service import call_llm

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt template — card and base_reason are injected by the engine,
# the LLM can only elaborate, never override.
# ---------------------------------------------------------------------------
_EXPLANATION_PROMPT = """You are AstraLLM, a professional financial advisor assistant.

A card recommendation decision has already been made by the rule engine.
Your ONLY task is to expand the base reasoning into a helpful, concise explanation
for the user. Do NOT suggest a different card. Do NOT hallucinate benefits.

Card Recommended: {card}
Base Reason: {base_reason}
User Query: {query}

Write 1–2 sentences that explain why this card is ideal for the user's specific situation.
Be specific, professional, and factual. Do not use bullet points."""


def explain_decision(decision: CardDecision, query: str) -> str:
    """
    Call the LLM to expand ``decision.base_reason`` into a fuller explanation.

    Falls back to ``decision.base_reason`` if the LLM is unavailable or
    returns an empty response, guaranteeing we always have a valid answer.
    """
    prompt = _EXPLANATION_PROMPT.format(
        card=decision.card,
        base_reason=decision.base_reason,
        query=query,
    )
    try:
        explanation = call_llm(prompt, temperature=0.2)
        if explanation and explanation.strip():
            logger.info("card_explainer.llm_ok card=%s", decision.card)
            return explanation.strip()
        logger.warning("card_explainer.llm_empty — using base_reason fallback")
    except Exception as exc:
        logger.warning("card_explainer.llm_error — using base_reason fallback: %s", exc)

    # Graceful fallback: base_reason is always correct
    return decision.base_reason

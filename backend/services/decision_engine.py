"""
Decision Engine — deterministic, rule-based card recommendation.

This module is the single source of truth for card selection.
The LLM is NEVER involved in this decision; it is used only for
explanation expansion after the decision has been made here.

Rule priority is top-to-bottom (first match wins).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CardDecision:
    """Immutable result produced by the decision engine."""

    card: str
    base_reason: str
    matched_rule: str


# ---------------------------------------------------------------------------
# Rule table — ordered by specificity (more specific rules first).
# Each entry: (rule_name, keywords, card_name, base_reason)
# ---------------------------------------------------------------------------
_RULES: list[tuple[str, tuple[str, ...], str, str]] = [
    (
        "online_shopping",
        ("amazon", "flipkart", "online", "iphone", "meesho", "myntra", "nykaa"),
        "SBI Cashback Card",
        "Offers 5% cashback on all online transactions including major e-commerce platforms",
    ),
    (
        "food_delivery",
        ("swiggy", "zomato", "food", "blinkit", "zepto", "dunzo", "instamart"),
        "HDFC Swiggy Credit Card",
        "Best card for food delivery with up to 10% cashback on Swiggy and partner apps",
    ),
    (
        "travel_international",
        ("travel", "bali", "international", "forex", "trip", "flight", "hotel",
         "airport", "lounge", "visa", "passport", "abroad", "holiday"),
        "Scapia Federal Credit Card",
        "Zero forex markup on international transactions plus complimentary airport lounge access",
    ),
]


def run_decision_engine(query: str) -> Optional[CardDecision]:
    """
    Evaluate the query against the rule table.

    Returns a :class:`CardDecision` on the first rule that matches,
    or ``None`` if no rule applies (caller handles the fallback).
    """
    text = (query or "").lower().strip()
    if not text:
        return None

    for rule_name, keywords, card_name, base_reason in _RULES:
        matched_kws = [kw for kw in keywords if kw in text]
        if matched_kws:
            logger.info(
                "decision_engine.match rule=%s card=%s matched_kws=%s",
                rule_name,
                card_name,
                matched_kws,
            )
            return CardDecision(
                card=card_name,
                base_reason=base_reason,
                matched_rule=rule_name,
            )

    logger.info("decision_engine.no_match query=%r", text[:80])
    return None

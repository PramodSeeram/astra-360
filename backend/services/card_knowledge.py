"""Hybrid card knowledge: structured base facts (always) + optional Qdrant RAG in card_node.

Spend routing and savings math stay in Python (canonical_cards + nodes); this module
only supplies product-oriented copy for the LLM.
"""

from __future__ import annotations

from typing import Any, Dict, List

from services.canonical_cards import CANONICAL_CARD_SPECS

# Mirrors the three canonical DB cards; kept in sync with CANONICAL_CARD_SPECS (last4 / bank / type).
CANONICAL_CARD_KNOWLEDGE: List[Dict[str, Any]] = [
    {
        "bank_name": "HDFC Bank",
        "card_type": "Swiggy Credit Card",
        "last4": "2109",
        "best_for": ["Food delivery (Swiggy, Zomato)", "Online food orders"],
        "typical_benefits": "Often positioned as a food-delivery co-brand; check issuer T&Cs for current cashback or reward rates.",
        "avoid_or_limit": "Not intended as a primary travel or offline-spend card; compare with your travel card for flights/hotels.",
        "notes": "When the user’s Swiggy/Zomato spend is already on this card, usage is usually well aligned for that category.",
    },
    {
        "bank_name": "Federal Bank",
        "card_type": "Swiggy Credit Card",
        "last4": "8765",
        "best_for": ["Food delivery (Swiggy, Zomato)", "Dining apps where supported"],
        "typical_benefits": "Co-brand positioning similar to Swiggy; issuer may change offers. Use only as supporting context, not as a fixed rate.",
        "avoid_or_limit": "Avoid assuming it beats travel cards for flights or forex spends.",
        "notes": "Use together with DB spend: which card actually saw Swiggy debits this month.",
    },
    {
        "bank_name": "SBI",
        "card_type": "Cashback Credit Card",
        "last4": "4321",
        "best_for": ["General online shopping", "Amazon/e-commerce where applicable", "Everyday spend"],
        "typical_benefits": "Cashback-style positioning; rates and caps vary by issuer and change over time.",
        "avoid_or_limit": "Not specialized for food delivery Swiggy vs HDFC/Federal Swiggy in the same wallet.",
        "notes": "Good default when Amazon or broad online spend appears in transaction data.",
    },
]


def get_inline_card_knowledge() -> Dict[str, Any]:
    """Always-on structured knowledge for the card agent (no network)."""
    return {
        "product_cards": [
            {k: v for k, v in row.items() if k != "notes"}
            for row in CANONICAL_CARD_KNOWLEDGE
        ],
        "full_detail": CANONICAL_CARD_KNOWLEDGE,
        "canonical_last4": [spec[2] for spec in CANONICAL_CARD_SPECS],
        "usage_rules": (
            "Spends, limits, and balances come only from user data. "
            "These bullets describe typical product positioning; never invent specific cashback % unless present in "
            "rag_context or card_knowledge_base. Prefer user transaction patterns over generic card marketing."
        ),
    }

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


_SUBSCRIPTION_KEYWORDS = (
    "netflix", "spotify", "prime video", "amazon prime", "youtube premium",
    "hotstar", "disney", "zee5", "sonyliv", "apple music", "apple tv",
    "openai", "chatgpt", "cursor", "github", "notion", "canva",
)

_UTILITY_KEYWORDS = (
    "electricity", "power", "bescom", "tneb", "bses", "mseb", "torrent power",
    "adani electricity", "water bill", "water supply", "gas bill", "piped gas",
    "indane", "hp gas", "bharat gas",
)

_CONNECTIVITY_KEYWORDS = (
    "jio", "airtel", "bsnl", "vi ", "vodafone", "idea", "wifi", "broadband",
    "fiber", "internet bill", "recharge",
)

_RENT_KEYWORDS = (
    "rent", "house rent", "flat rent", "pg rent", "hostel rent",
    "nobroker", "magicbricks", "housing.com",
)


def classify_billing(description: str) -> Optional[str]:
    """Return the billing category for a transaction description, or None if not a bill."""
    desc = (description or "").lower()
    if any(k in desc for k in _SUBSCRIPTION_KEYWORDS):
        return "subscription"
    if any(k in desc for k in _UTILITY_KEYWORDS):
        return "utility"
    if any(k in desc for k in _CONNECTIVITY_KEYWORDS):
        return "connectivity"
    if any(k in desc for k in _RENT_KEYWORDS):
        return "rent"
    return None


_SERVICE_NAME_MAP = (
    # OTT / Streaming
    ("netflix", "Netflix"),
    ("spotify", "Spotify"),
    ("hotstar", "Disney+ Hotstar"),
    ("disney", "Disney+ Hotstar"),
    ("prime video", "Amazon Prime Video"),
    ("amazon prime", "Amazon Prime"),
    ("youtube premium", "YouTube Premium"),
    ("zee5", "ZEE5"),
    ("sonyliv", "SonyLIV"),
    ("apple music", "Apple Music"),
    ("apple tv", "Apple TV+"),
    # Connectivity
    ("jio fiber", "Jio Fiber"),
    ("jio recharge", "Jio Mobile"),
    ("jio", "Jio"),
    ("airtel fiber", "Airtel Fiber"),
    ("airtel", "Airtel"),
    ("bsnl", "BSNL"),
    ("vodafone", "Vodafone Vi"),
    ("broadband", "Broadband"),
    # Utilities
    ("bescom", "BESCOM Electricity"),
    ("tneb", "TNEB Electricity"),
    ("bses", "BSES Electricity"),
    ("mseb", "MSEB Electricity"),
    ("electricity", "Electricity"),
    ("piped gas", "Piped Gas"),
    ("indane", "Indane Gas"),
    ("hp gas", "HP Gas"),
    ("bharat gas", "Bharat Gas"),
    ("water", "Water Bill"),
    # Rent
    ("nobroker", "NoBroker"),
    ("rent", "Rent"),
)


def _merchant_key(description: str) -> str:
    """Derive a human-readable service name from a raw transaction description."""
    desc_lower = (description or "").lower()
    for keyword, label in _SERVICE_NAME_MAP:
        if keyword in desc_lower:
            return label
    # Fallback: take first 2 meaningful words from description, skip UPI prefixes
    line = (description or "").strip().split("\n")[0].strip()
    line = re.sub(r"\s+", " ", line)
    # Strip common UPI noise prefixes like "UPI/", "NACH/", numbers
    line = re.sub(r"(?i)^(upi|nach|neft|imps|rtgs)[/_-]", "", line).strip()
    line = re.sub(r"/\d{6,}.*", "", line).strip()  # strip trailing ref numbers
    words = [w for w in line.split() if not re.match(r"^\d+$", w)]
    return " ".join(words[:3]).title() if words else "Unknown"


def compute_billing(transactions: List[Any]) -> Dict[str, Any]:
    """
    Aggregate billing/subscription/utility amounts from a list of Transaction ORM objects
    or plain dicts that have `description` and `amount` fields.
    """
    result: Dict[str, Any] = {
        "subscriptions": {},
        "utilities": {},
        "connectivity": {},
        "rent": 0.0,
        "total": 0.0,
    }

    for tx in transactions:
        if hasattr(tx, "description"):
            desc = tx.description or ""
            amount = float(tx.amount or 0)
        elif isinstance(tx, dict):
            desc = tx.get("description") or ""
            amount = float(tx.get("amount") or 0)
        else:
            continue

        # Only debit / expense entries (negative amounts mean money left account)
        amount = abs(amount) if amount < 0 else amount
        if amount <= 0:
            continue

        category = classify_billing(desc)
        if not category:
            continue

        merchant = _merchant_key(desc)

        if category == "rent":
            result["rent"] = result["rent"] + amount
        elif category == "subscription":
            prev = result["subscriptions"].get(merchant, 0.0)
            result["subscriptions"][merchant] = prev + amount
        elif category == "utility":
            prev = result["utilities"].get(merchant, 0.0)
            result["utilities"][merchant] = prev + amount
        elif category == "connectivity":
            prev = result["connectivity"].get(merchant, 0.0)
            result["connectivity"][merchant] = prev + amount

        result["total"] += amount

    return result

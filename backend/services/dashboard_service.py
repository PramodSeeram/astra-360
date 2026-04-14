"""
Dashboard Service Layer — Phase 2
Reads from in-memory user_store and returns structured responses.
All data access uses safe .get() with fallbacks.
Centralized has_data flag drives empty-state logic.
"""

import time
from services.user_service import user_store


def _get_user_safe(user_id: str) -> dict | None:
    """Safely retrieve user from store."""
    return user_store.get(user_id)


def _has_data(user: dict) -> bool:
    """Centralized has_data check."""
    return user.get("has_data", False)


def _get_financial_data(user: dict) -> dict:
    """Safely get financial_data with fallback to empty dict."""
    return user.get("financial_data", {})


def _timestamp_to_iso(ts: float | None) -> str | None:
    """Convert unix timestamp to ISO string, or None."""
    if ts is None:
        return None
    try:
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(ts))
    except (OSError, ValueError):
        return None


# ----------------------------------------------
# HOME SUMMARY
# ----------------------------------------------
def get_home_data(user_id: str) -> dict | None:
    user = _get_user_safe(user_id)
    if not user:
        return None

    has_data = _has_data(user)
    data = _get_financial_data(user)
    kyc = user.get("kyc", {})

    first_name = kyc.get("first_name", "User")
    last_name = kyc.get("last_name", "")
    initials = (first_name[:1] + last_name[:1]).upper() if last_name else first_name[:2].upper()

    result = {
        "user_id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "initials": initials,
        "balance": data.get("balance", 0),
        "savings": data.get("savings", 0),
        "investments": data.get("investments", 0),
        "credit_due": data.get("credit_due", 0),
        "credit_score": data.get("credit_score", 0),
        "insights": data.get("insights", []),
        "has_data": has_data,
        "source": "processed_data" if has_data else "empty_state",
        "last_updated": _timestamp_to_iso(data.get("initialized_at")),
        "data_sources": data.get("data_sources", []),
        "message": None if has_data else "Upload your financial documents to get started. We'll analyze your accounts, investments, and bills to give you personalized AI insights.",
    }

    print(f"  [DASHBOARD] GET /home -> user={user_id}, has_data={has_data}, balance={result['balance']}")
    return result


# ----------------------------------------------
# BILLS & SUBSCRIPTIONS
# ----------------------------------------------
def get_bills_data(user_id: str) -> dict | None:
    user = _get_user_safe(user_id)
    if not user:
        return None

    has_data = _has_data(user)
    data = _get_financial_data(user)

    subscriptions = data.get("subscriptions", [])
    bills = data.get("bills", [])

    total_monthly = sum(s.get("amount", 0) for s in subscriptions) + sum(b.get("amount", 0) for b in bills)

    result = {
        "subscriptions": subscriptions,
        "utilities": bills,
        "total_monthly": total_monthly,
        "due_this_week": 0,
        "has_data": has_data,
        "source": "processed_data" if has_data else "empty_state",
        "last_updated": _timestamp_to_iso(data.get("initialized_at")),
        "data_sources": data.get("data_sources", []),
        "message": None if has_data else "No bills yet. Upload your bank statements to auto-detect subscriptions and bills.",
    }

    print(f"  [DASHBOARD] GET /bills -> user={user_id}, has_data={has_data}, subs={len(subscriptions)}, bills={len(bills)}")
    return result


# ----------------------------------------------
# CARDS
# ----------------------------------------------
def get_cards_data(user_id: str) -> dict | None:
    user = _get_user_safe(user_id)
    if not user:
        return None

    has_data = _has_data(user)
    data = _get_financial_data(user)

    cards = data.get("cards", [])
    transactions = data.get("transactions", [])

    result = {
        "cards": cards,
        "transactions": transactions,
        "has_data": has_data,
        "source": "processed_data" if has_data else "empty_state",
        "last_updated": _timestamp_to_iso(data.get("initialized_at")),
        "data_sources": data.get("data_sources", []),
        "message": None if has_data else "No cards available. Link your bank accounts to see your cards here.",
    }

    print(f"  [DASHBOARD] GET /cards -> user={user_id}, has_data={has_data}, cards={len(cards)}")
    return result


# ----------------------------------------------
# CALENDAR
# ----------------------------------------------
def get_calendar_data(user_id: str) -> dict | None:
    user = _get_user_safe(user_id)
    if not user:
        return None

    has_data = _has_data(user)
    data = _get_financial_data(user)

    events = data.get("calendar", [])

    result = {
        "events": events,
        "has_data": has_data,
        "source": "processed_data" if has_data else "empty_state",
        "last_updated": _timestamp_to_iso(data.get("initialized_at")),
        "data_sources": data.get("data_sources", []),
        "message": None if has_data else "No financial events yet. Your bill due dates, SIP debits, and EMIs will appear here automatically.",
    }

    print(f"  [DASHBOARD] GET /calendar -> user={user_id}, has_data={has_data}, events={len(events)}")
    return result


# ----------------------------------------------
# PROFILE
# ----------------------------------------------
def get_profile_data(user_id: str) -> dict | None:
    user = _get_user_safe(user_id)
    if not user:
        return None

    kyc = user.get("kyc", {})
    has_data = _has_data(user)
    data = _get_financial_data(user)

    first_name = kyc.get("first_name", "User")
    last_name = kyc.get("last_name", "")
    pan = kyc.get("pan", "")
    pan_masked = f"{'*' * 6}{pan[-4:]}" if len(pan) >= 4 else ""

    initials = (first_name[:1] + last_name[:1]).upper() if last_name else first_name[:2].upper()

    created_at = user.get("created_at")
    joined_str = _timestamp_to_iso(created_at)

    result = {
        "user_id": user_id,
        "first_name": first_name,
        "last_name": last_name,
        "full_name": f"{first_name} {last_name}".strip(),
        "initials": initials,
        "phone": user.get("phone", ""),
        "email": kyc.get("email", ""),
        "pan_masked": pan_masked,
        "pan_type": kyc.get("pan_type", ""),
        "is_onboarded": user.get("is_onboarded", False),
        "linked_accounts": data.get("linked_accounts", []),
        "has_data": has_data,
        "source": "processed_data" if has_data else "empty_state",
        "joined_at": joined_str,
        "data_sources": data.get("data_sources", []),
        "message": None if has_data else "Link your bank accounts via Account Aggregator to see them here.",
    }

    print(f"  [DASHBOARD] GET /profile -> user={user_id}, name={first_name} {last_name}, has_data={has_data}")
    return result

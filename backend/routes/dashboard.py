"""
Dashboard Routes — Phase 2
GET endpoints that return structured JSON for each dashboard screen.
All routes validate user existence and return clean empty-state data.
"""

from fastapi import APIRouter, HTTPException, Query
from services.dashboard_service import (
    get_home_data,
    get_bills_data,
    get_cards_data,
    get_calendar_data,
    get_profile_data,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _validate_user_id(user_id: str) -> str:
    """Validate user_id is provided and not empty."""
    if not user_id or not user_id.strip():
        raise HTTPException(status_code=400, detail="user_id is required.")
    return user_id.strip()


def _user_not_found():
    """Standard 404 for missing users."""
    raise HTTPException(status_code=404, detail="User not found.")


@router.get("/home")
def dashboard_home(user_id: str = Query(..., description="User ID")):
    uid = _validate_user_id(user_id)
    result = get_home_data(uid)
    if result is None:
        _user_not_found()
    return result


@router.get("/bills")
def dashboard_bills(user_id: str = Query(..., description="User ID")):
    uid = _validate_user_id(user_id)
    result = get_bills_data(uid)
    if result is None:
        _user_not_found()
    return result


@router.get("/cards")
def dashboard_cards(user_id: str = Query(..., description="User ID")):
    uid = _validate_user_id(user_id)
    result = get_cards_data(uid)
    if result is None:
        _user_not_found()
    return result


@router.get("/calendar")
def dashboard_calendar(user_id: str = Query(..., description="User ID")):
    uid = _validate_user_id(user_id)
    result = get_calendar_data(uid)
    if result is None:
        _user_not_found()
    return result


@router.get("/profile")
def dashboard_profile(user_id: str = Query(..., description="User ID")):
    uid = _validate_user_id(user_id)
    result = get_profile_data(uid)
    if result is None:
        _user_not_found()
    return result

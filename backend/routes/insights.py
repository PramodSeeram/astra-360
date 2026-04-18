from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from database import get_db
from models import get_user_by_external_id
from services.brain_insights_service import get_latest_insights, prepend_processing_banner
from services.user_state import get_user_state

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/latest")
def latest_insights(
    user_id: str = Query(..., description="User ID"),
    db: Session = Depends(get_db),
):
    external_id = user_id.strip()
    if not external_id:
        raise HTTPException(status_code=400, detail="user_id is required.")

    user = get_user_by_external_id(db, external_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    state = get_user_state(db, user)
    if state not in ("ACTIVE", "PARTIAL"):
        return {"insights": []}

    insights = get_latest_insights(db, user, limit=6)
    if state == "PARTIAL" and insights:
        insights = prepend_processing_banner(insights)
    return {"insights": insights}

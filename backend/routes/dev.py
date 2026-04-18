from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Transaction, User, get_user_by_external_id
from services.dev_data import ACTIVE_DEMO_USER_ID, DEMO_USERS, seed_demo_data
from services.dev_state import get_active_user_id, set_active_user_id


router = APIRouter(prefix="/dev", tags=["dev"])


class SwitchUserRequest(BaseModel):
    user_id: str


def _resolve_user_id(explicit_user_id: str | None, header_user_id: str | None) -> str:
    user_id = (explicit_user_id or header_user_id or get_active_user_id()).strip()
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required.")
    return user_id


@router.get("/seed")
def seed_dev_data(db: Session = Depends(get_db)):
    result = seed_demo_data(db)
    set_active_user_id(ACTIVE_DEMO_USER_ID)
    return result


@router.get("/users")
def list_demo_users(db: Session = Depends(get_db)):
    active_user_id = get_active_user_id()
    users = []
    for payload in DEMO_USERS:
        user = get_user_by_external_id(db, payload["user_id"])
        users.append(
            {
                "user_id": payload["user_id"],
                "name": payload["name"],
                "income": float(payload.get("income", 0) or 0),
                "emi": float(payload.get("emi", 0) or 0),
                "seeded": user is not None,
                "active": payload["user_id"] == active_user_id,
            }
        )
    return {"active_user_id": active_user_id, "users": users}


@router.post("/switch-user")
def switch_demo_user(request: SwitchUserRequest, db: Session = Depends(get_db)):
    user_id = request.user_id.strip()
    user = get_user_by_external_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    set_active_user_id(user_id)
    return {
        "status": "ok",
        "active_user_id": user_id,
        "name": user.name,
    }


@router.get("/user-state")
def get_dev_user_state(
    user_id: str | None = None,
    x_user_id: str | None = Header(default=None, alias="x-user-id"),
    db: Session = Depends(get_db),
):
    resolved_user_id = _resolve_user_id(user_id, x_user_id)
    user = get_user_by_external_id(db, resolved_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    credit_account = user.credit_accounts[0] if user.credit_accounts else None
    return {
        "user_id": user.external_id,
        "income": float(user.monthly_income or 0),
        "emi": float(user.financial_summary.emi_total if user.financial_summary else 0.0),
        "credit": (
            {
                "limit": float(credit_account.credit_limit or 0),
                "used": float(credit_account.used_amount or 0),
            }
            if credit_account
            else None
        ),
        "transactions_count": db.query(Transaction).filter(Transaction.user_id == user.id).count(),
    }

import asyncio
import random
from fastapi import APIRouter, HTTPException
from app_schemas.schemas import ScanRequest, ScanResponse
from models import Card, get_user_by_external_id
from services.canonical_cards import CANONICAL_CARD_SPECS
from database import get_db
from services.dashboard_service import build_mock_cibil
from sqlalchemy.orm import Session
from fastapi import Depends

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

SCAN_STEPS = [
    "Verifying identity...",
    "Fetching linked bank accounts...",
    "Pulling CIBIL credit report...",
    "Scanning loans, FDs & investments...",
    "Financial profile ready!",
]


@router.post("/scan", response_model=ScanResponse)
async def scan(req: ScanRequest, db: Session = Depends(get_db)):
    user = get_user_by_external_id(db, req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    for step in SCAN_STEPS:
        print(f"  [SCAN] {step}")
        await asyncio.sleep(random.uniform(0.8, 1.0))

    # Generate a deterministic mock CIBIL so the dashboard can show a
    # realistic score immediately after KYC finishes.
    cibil = build_mock_cibil(user)
    if cibil:
        user.credit_score = cibil["score"]
    elif not user.credit_score:
        user.credit_score = 731

    existing_cards = db.query(Card).filter(Card.user_id == user.id).count()
    if existing_cards == 0:
        for bank_name, card_type, last4_digits, limit_value, _balance in CANONICAL_CARD_SPECS:
            db.add(
                Card(
                    user_id=user.id,
                    bank_name=bank_name,
                    card_type=card_type,
                    last4_digits=last4_digits,
                    limit=limit_value,
                    balance=0.0,
                )
            )
    db.commit()

    print(f"\n  [SCAN] Complete for {req.user_id}\n")

    return ScanResponse(status="scan_complete")

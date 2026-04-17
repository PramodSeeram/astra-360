import asyncio
import random
from fastapi import APIRouter, HTTPException
from app_schemas.schemas import ScanRequest, ScanResponse
from models import get_user_by_external_id
from database import get_db
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

    # init_financial_data(req.user_id) # Skip in-memory initialization

    print(f"\n  [SCAN] Complete for {req.user_id}\n")

    return ScanResponse(status="scan_complete")

import asyncio
import random
from fastapi import APIRouter, HTTPException
from models.schemas import ScanRequest, ScanResponse
from services.user_service import get_user, init_financial_data

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

SCAN_STEPS = [
    "Verifying identity...",
    "Fetching linked bank accounts...",
    "Pulling CIBIL credit report...",
    "Scanning loans, FDs & investments...",
    "Financial profile ready!",
]


@router.post("/scan", response_model=ScanResponse)
async def scan(req: ScanRequest):
    user = get_user(req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    for step in SCAN_STEPS:
        print(f"  [SCAN] {step}")
        await asyncio.sleep(random.uniform(0.8, 1.0))

    init_financial_data(req.user_id)

    print(f"\n  [SCAN] Complete for {req.user_id}\n")

    return ScanResponse(status="scan_complete")

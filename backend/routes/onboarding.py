from fastapi import APIRouter, HTTPException
from models.schemas import ScanRequest
from services.user_service import get_user
import asyncio
import random

router = APIRouter()

@router.post("/scan")
async def scan(request: ScanRequest):
    user_id = request.user_id
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await asyncio.sleep(random.uniform(1, 1.5))
    financial_data = {
        "balance": 0,
        "savings": 0,
        "investments": 0,
        "credit_due": 0,
        "transactions": [],
        "subscriptions": [],
        "bills": [],
        "insights": [],
        "calendar": []
    }
    user['financial_data'] = financial_data
    return {"status": "scan_complete"}
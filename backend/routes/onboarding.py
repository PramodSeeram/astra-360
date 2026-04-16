import asyncio
from fastapi import APIRouter, HTTPException
from ..models.schemas import ScanRequest
from ..services.user_service import get_user
from ..services.persona_service import prepare_user_data

router = APIRouter()

@router.post("/scan")
async def scan_user(request: ScanRequest):
    user_id = request.user_id
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await asyncio.sleep(1.2)  # Simulate processing delay
    financial_data = prepare_user_data(user_id)
    user['financial_data'] = financial_data
    return {"status": "scan_complete"}
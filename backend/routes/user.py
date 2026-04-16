from fastapi import APIRouter, HTTPException
from ..models.schemas import KYCRequest
from ..services.user_service import get_user, save_kyc
from ..utils.validators import validate_pan, get_pan_type

router = APIRouter()

@router.post("/kyc")
async def submit_kyc(request: KYCRequest):
    user_id = request.user_id
    user = get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not request.first_name or not request.last_name or not request.pan:
        raise HTTPException(status_code=400, detail="Required fields missing")
    if not validate_pan(request.pan):
        raise HTTPException(status_code=400, detail="Invalid PAN")
    pan_type = get_pan_type(request.pan)
    kyc_data = {
        "first_name": request.first_name,
        "last_name": request.last_name,
        "email": request.email,
        "pan": request.pan,
        "pan_type": pan_type
    }
    save_kyc(user_id, kyc_data)
    return {"status": "kyc_completed", "pan_type": pan_type}
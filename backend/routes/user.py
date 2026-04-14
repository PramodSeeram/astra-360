from fastapi import APIRouter, HTTPException
from models.schemas import KycRequest, KycResponse
from services.user_service import get_user, update_kyc
from utils.validators import validate_pan, get_pan_type

router = APIRouter(prefix="/api/user", tags=["user"])


@router.post("/kyc", response_model=KycResponse)
def submit_kyc(req: KycRequest):
    user = get_user(req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if not validate_pan(req.pan):
        raise HTTPException(status_code=400, detail="Invalid PAN format. Expected: ABCDE1234F")

    pan_type = get_pan_type(req.pan)

    kyc_data = {
        "first_name": req.first_name,
        "last_name": req.last_name,
        "email": req.email,
        "pan": req.pan,
        "pan_type": pan_type,
    }

    update_kyc(req.user_id, kyc_data)

    print(f"\n{'='*40}")
    print(f"  [KYC] {req.first_name} {req.last_name}")
    print(f"  [PAN] {req.pan} → {pan_type}")
    print(f"{'='*40}\n")

    return KycResponse(status="kyc_completed", pan_type=pan_type)

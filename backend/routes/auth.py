from fastapi import APIRouter, HTTPException
from models.schemas import SendOtpRequest, SendOtpResponse, VerifyOtpRequest, VerifyOtpResponse
from services.otp_service import generate_otp, verify_otp
from services.user_service import create_or_get_user
from utils.validators import validate_phone

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/send-otp", response_model=SendOtpResponse)
def send_otp(req: SendOtpRequest):
    if not validate_phone(req.phone):
        raise HTTPException(status_code=400, detail="Invalid phone number. Must be 10 digits starting with 6-9.")

    result = generate_otp(req.phone)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return SendOtpResponse(status="otp_sent", dev_otp=result["otp"])


@router.post("/verify-otp", response_model=VerifyOtpResponse)
def verify_otp_route(req: VerifyOtpRequest):
    if not validate_phone(req.phone):
        raise HTTPException(status_code=400, detail="Invalid phone number.")

    result = verify_otp(req.phone, req.otp)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    user_id = create_or_get_user(req.phone)
    return VerifyOtpResponse(status="verified", user_id=user_id)

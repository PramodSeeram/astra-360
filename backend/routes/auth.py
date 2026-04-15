from fastapi import APIRouter, HTTPException
from models.schemas import SendOTPRequest, VerifyOTPRequest
from services.otp_service import generate_otp, verify_otp, can_resend
from services.user_service import create_user

router = APIRouter()

@router.post("/send-otp")
async def send_otp(request: SendOTPRequest):
    phone = request.phone
    if not can_resend(phone):
        raise HTTPException(status_code=429, detail="Resend not available yet")
    otp = generate_otp(phone)
    return {"status": "otp_sent", "dev_otp": otp}

@router.post("/verify-otp")
async def verify_otp_endpoint(request: VerifyOTPRequest):
    phone = request.phone
    otp = request.otp
    if not verify_otp(phone, otp):
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")
    user_id = create_user(phone)
    return {"status": "verified", "user_id": user_id}
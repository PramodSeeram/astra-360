from fastapi import APIRouter, HTTPException, BackgroundTasks
from app_schemas.schemas import SendOtpRequest, SendOtpResponse, VerifyOtpRequest, VerifyOtpResponse, DemoLoginRequest, DemoLoginResponse
from services.otp_service import generate_otp, verify_otp
from services.user_service import create_or_get_user
from utils.validators import validate_phone
from models import User
from database import get_db
from sqlalchemy.orm import Session
from fastapi import Depends

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/send-otp", response_model=SendOtpResponse)
def send_otp(req: SendOtpRequest, background_tasks: BackgroundTasks):
    if not validate_phone(req.phone):
        raise HTTPException(status_code=400, detail="Invalid phone number. Must be 10 digits starting with 6-9.")

    # We still want the OTP to return dev_otp immediately for dev purposes, 
    # but the REAL sending can happen in background.
    result = generate_otp(req.phone, background_tasks=background_tasks)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    return SendOtpResponse(status="otp_sent", dev_otp=result["otp"])


@router.post("/verify-otp", response_model=VerifyOtpResponse)
def verify_otp_route(req: VerifyOtpRequest, db: Session = Depends(get_db)):
    if not validate_phone(req.phone):
        raise HTTPException(status_code=400, detail="Invalid phone number.")

    result = verify_otp(req.phone, req.otp)

    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])

    # MySQL User Creation
    user = db.query(User).filter(User.phone_number == req.phone).first()
    if not user:
        import uuid
        external_id = f"user_{req.phone[-3:]}_{uuid.uuid4().hex[:4]}"
        user = User(
            external_id=external_id,
            name="New User",
            phone_number=req.phone,
            credit_score=0
        )
        db.add(user)
        db.commit()
        db.refresh(user)

    return VerifyOtpResponse(status="verified", user_id=user.external_id)

@router.post("/demo-login", response_model=DemoLoginResponse)
def demo_login(req: DemoLoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.phone_number == req.phone).first()
    if not user:
        # Revert to 404 to trigger onboarding flow
        raise HTTPException(status_code=404, detail="User not found with this phone number.")
    
    return DemoLoginResponse(
        user_id=user.external_id,
        name=user.name,
        status="success"
    )

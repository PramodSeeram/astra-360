from fastapi import APIRouter, HTTPException, Depends
from app_schemas.schemas import KycRequest, KycResponse
from utils.validators import validate_pan, get_pan_type
from models import get_user_by_external_id
from database import get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/user", tags=["user"])

@router.post("/kyc", response_model=KycResponse)
def submit_kyc(req: KycRequest, db: Session = Depends(get_db)):
    user = get_user_by_external_id(db, req.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    if not validate_pan(req.pan):
        raise HTTPException(status_code=400, detail="Invalid PAN format. Expected: ABCDE1234F")

    pan_type = get_pan_type(req.pan)

    # Update MySQL User
    user.name = f"{req.first_name} {req.last_name}"
    user.email = req.email
    # You might want to store PAN in a separate column or just update the user record
    # For now, let's just update the name and email
    
    db.commit()

    print(f"\n{'='*40}")
    print(f"  [KYC SAVED TO MYSQL] {user.name}")
    print(f"  [PAN] {req.pan} -> {pan_type}")
    print(f"{'='*40}\n")

    return KycResponse(status="kyc_completed", pan_type=pan_type)

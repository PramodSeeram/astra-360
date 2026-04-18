import os
import shutil
import hashlib
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from models import User, get_user_by_external_id, UserProcessingStatus
from services.data_activation_service import process_upload_safe

router = APIRouter(tags=["Data Activation"])

UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


def _safe_upload_filename(filename: str | None) -> str:
    safe_name = Path(filename or "").name.strip()
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid file name")
    return safe_name


def _get_or_create_upload_user(db: Session, external_id: str) -> User:
    user = get_user_by_external_id(db, external_id)
    if user:
        return user

    phone_suffix = hashlib.sha256(external_id.encode()).hexdigest()[:10]
    user = User(
        external_id=external_id,
        name="Upload User",
        phone_number=f"upload_{phone_suffix}",
        credit_score=0,
        monthly_income=0.0,
        risk_level="unknown",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/data/upload")
async def upload_data(
    background_tasks: BackgroundTasks,
    user_id: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Accepts a bank statement (PDF/CSV), saves it, and triggers
    background processing for activation.
    """
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        raise HTTPException(status_code=400, detail="Invalid user")

    user = _get_or_create_upload_user(db, normalized_user_id)
    safe_filename = _safe_upload_filename(file.filename)

    # 1. Save File
    file_path = os.path.join(UPLOAD_DIR, f"{normalized_user_id}_{safe_filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. Reset/Initialize Status
    status = db.query(UserProcessingStatus).filter_by(user_id=user.id).first()
    if not status:
        status = UserProcessingStatus(user_id=user.id)
        db.add(status)
    
    status.status = "processing"
    status.progress = 5
    status.stage = "File uploaded, starting analysis..."
    status.error_message = None
    db.commit()

    # 3. Queue Background Task
    background_tasks.add_task(process_upload_safe, normalized_user_id, file_path, safe_filename)

    return {
        "status": "processing",
        "message": "Analysis started in background. Polling authorized.",
        "user_id": normalized_user_id
    }

@router.get("/api/data/status")
def get_activation_status(user_id: str, db: Session = Depends(get_db)):
    """
    Polling endpoint for UI to track activation progress.
    """
    normalized_user_id = user_id.strip()
    if not normalized_user_id:
        raise HTTPException(status_code=400, detail="Invalid user")

    user = _get_or_create_upload_user(db, normalized_user_id)
    
    status = db.query(UserProcessingStatus).filter_by(user_id=user.id).first()
    if not status:
        return {"status": "idle", "progress": 0, "stage": "Waiting for upload"}
    
    return {
        "status": status.status,
        "progress": status.progress,
        "stage": status.stage,
        "error": status.error_message
    }

import os
import shutil
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from database import get_db
from models import get_user_by_external_id, UserProcessingStatus
from services.data_activation_service import process_upload_safe

router = APIRouter(tags=["Data Activation"])

UPLOAD_DIR = "temp_uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

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
    user = get_user_by_external_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # 1. Save File
    file_path = os.path.join(UPLOAD_DIR, f"{user_id}_{file.filename}")
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
    background_tasks.add_task(process_upload_safe, user_id, file_path, file.filename)

    return {
        "status": "processing",
        "message": "Analysis started in background. Polling authorized.",
        "user_id": user_id
    }

@router.get("/api/data/status")
def get_activation_status(user_id: str, db: Session = Depends(get_db)):
    """
    Polling endpoint for UI to track activation progress.
    """
    user = get_user_by_external_id(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    status = db.query(UserProcessingStatus).filter_by(user_id=user.id).first()
    if not status:
        return {"status": "idle", "progress": 0, "stage": "Waiting for upload"}
    
    return {
        "status": status.status,
        "progress": status.progress,
        "stage": status.stage,
        "error": status.error_message
    }

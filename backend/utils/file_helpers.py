import os
import shutil
from fastapi import UploadFile

UPLOAD_DIR = "temp_uploads"

def save_upload_file_tmp(upload_file: UploadFile) -> str:
    """Saves the uploaded file temporarily and returns the file path."""
    if not os.path.exists(UPLOAD_DIR):
        os.makedirs(UPLOAD_DIR)
    
    file_path = os.path.join(UPLOAD_DIR, upload_file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(upload_file.file, buffer)
    return file_path

def remove_tmp_file(file_path: str):
    """Deletes the temporary file after processing."""
    if os.path.exists(file_path):
        os.remove(file_path)

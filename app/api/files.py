import os
import shutil
import uuid
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from app.api.deps import get_current_user
from app.models.models import User

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user)
):
    uploaded_files = []

    for file in files:
        try:
            # Generate a unique filename to prevent overwrites
            file_ext = os.path.splitext(file.filename)[1]
            unique_filename = f"{uuid.uuid4()}{file_ext}"
            file_path = os.path.join(UPLOAD_DIR, unique_filename)

            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)

            uploaded_files.append({
                "original_name": file.filename,
                "saved_name": unique_filename,
                "path": file_path,
                "size": os.path.getsize(file_path),
                "content_type": file.content_type
            })
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to save file {file.filename}: {str(e)}")
        finally:
            await file.close()

    return {"uploaded": uploaded_files}

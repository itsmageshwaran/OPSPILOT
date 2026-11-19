"""
File Upload Handling Route for OpsPilot.
Demonstrates:
1. Secure multipart file upload handling via FastAPI UploadFile
2. File extension allowlisting (.json, .log, .csv, .txt, .zip)
3. Maximum file size enforcement (10 MB)
4. Path traversal prevention using os.path.basename & sanitized UUID filenames
"""

import os
import time
import uuid
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, status

logger = logging.getLogger("opspilot.upload")

router = APIRouter(prefix="/api", tags=["File Upload Handling"])

UPLOAD_DIR = os.path.join(os.getcwd(), "data", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_UPLOAD_EXTENSIONS = {".json", ".log", ".csv", ".txt", ".zip"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/upload/telemetry-bundle",
    status_code=status.HTTP_201_CREATED,
    summary="Upload telemetry log bundle or incident diagnostic package"
)
@router.post(
    "/telemetry/upload-bundle",
    status_code=status.HTTP_201_CREATED,
    include_in_schema=False
)
async def upload_telemetry_bundle(file: UploadFile = File(...)):
    """
    Secure File Upload Handling:
    - Enforces extension allowlist (.json, .log, .csv, .txt, .zip)
    - Validates file size limit (10MB)
    - Defends against path traversal attacks
    """
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename cannot be empty"
        )

    # 1. Extension Allowlist Check
    clean_name = os.path.basename(file.filename)
    _, ext = os.path.splitext(clean_name)
    ext = ext.lower()

    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension '{ext}'. Disallowed file extension. Allowed extensions: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
        )

    # 2. File Read & Size Enforcement
    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB"
        )

    # 3. Path Traversal Defense: Unique sanitized destination
    safe_filename = f"bundle_{int(time.time())}_{uuid.uuid4().hex[:8]}{ext}"
    destination_path = os.path.join(UPLOAD_DIR, safe_filename)

    with open(destination_path, "wb") as f:
        f.write(content)

    logger.info(f"File uploaded successfully: {clean_name} -> {safe_filename} ({len(content)} bytes)")

    return {
        "status": "UPLOAD_SUCCESS",
        "original_filename": clean_name,
        "saved_as": safe_filename,
        "size_bytes": len(content),
        "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }

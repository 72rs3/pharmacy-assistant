from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

from app.db import BACKEND_DIR


LOCAL_UPLOAD_DIR = Path(os.getenv("PRESCRIPTION_UPLOAD_DIR", BACKEND_DIR / "uploads" / "prescriptions"))


@dataclass(frozen=True)
class StoredFile:
    location: str
    original_filename: str
    content_type: str | None


@dataclass(frozen=True)
class LoadedFile:
    body: bytes
    filename: str
    content_type: str


def _storage_backend() -> str:
    configured = os.getenv("PRESCRIPTION_STORAGE", "").strip().lower()
    if configured:
        return configured
    return "r2" if os.getenv("R2_BUCKET") else "local"


def _safe_filename(filename: str) -> str:
    return (filename or "upload").replace("/", "_").replace("\\", "_")


def _r2_client():
    try:
        import boto3  # type: ignore
    except ImportError as exc:
        raise RuntimeError("boto3 is required when PRESCRIPTION_STORAGE=r2") from exc

    account_id = os.getenv("R2_ACCOUNT_ID", "").strip()
    access_key_id = os.getenv("R2_ACCESS_KEY_ID", "").strip()
    secret_access_key = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
    endpoint_url = os.getenv("R2_ENDPOINT_URL", "").strip()
    if not endpoint_url and account_id:
        endpoint_url = f"https://{account_id}.r2.cloudflarestorage.com"
    if not endpoint_url or not access_key_id or not secret_access_key:
        raise RuntimeError("R2 endpoint and credentials are not configured")

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name=os.getenv("R2_REGION", "auto"),
    )


def save_prescription_upload(file: UploadFile, content: bytes, *, token: str, pharmacy_id: int) -> StoredFile:
    original_filename = file.filename or "upload"
    safe_name = _safe_filename(original_filename)
    backend = _storage_backend()

    if backend == "r2":
        bucket = os.getenv("R2_BUCKET", "").strip()
        if not bucket:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="R2 bucket is not configured")
        key = f"prescriptions/pharmacy-{int(pharmacy_id)}/{token}_{safe_name}"
        try:
            _r2_client().put_object(
                Bucket=bucket,
                Key=key,
                Body=content,
                ContentType=file.content_type or "application/octet-stream",
            )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to store upload") from exc
        return StoredFile(location=f"r2://{bucket}/{key}", original_filename=original_filename, content_type=file.content_type)

    LOCAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    dest = LOCAL_UPLOAD_DIR / f"{token}_{safe_name}"
    dest.write_bytes(content)
    return StoredFile(location=str(dest), original_filename=original_filename, content_type=file.content_type)


def load_prescription_file(location: str, *, original_filename: str | None, content_type: str | None) -> LoadedFile:
    if location.startswith("r2://"):
        without_scheme = location.removeprefix("r2://")
        bucket, _, key = without_scheme.partition("/")
        if not bucket or not key:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid stored file path")
        try:
            response = _r2_client().get_object(Bucket=bucket, Key=key)
            body = response["Body"].read()
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from exc
        return LoadedFile(
            body=body,
            filename=original_filename or Path(key).name,
            content_type=content_type or "application/octet-stream",
        )

    file_path = Path(location or "")
    try:
        resolved = file_path.resolve(strict=True)
        upload_root = LOCAL_UPLOAD_DIR.resolve(strict=False)
        if upload_root not in resolved.parents and resolved != upload_root:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file path")
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found") from exc

    return LoadedFile(
        body=resolved.read_bytes(),
        filename=original_filename or resolved.name,
        content_type=content_type or "application/octet-stream",
    )

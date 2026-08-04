"""AWS S3 helpers — pre-signed URL generation only.

The backend holds all AWS credentials; the mobile app never sees them.
All uploads go through a short-lived pre-signed PUT URL; all reads go
through a short-lived pre-signed GET URL.
"""
from __future__ import annotations

import mimetypes
import uuid
from typing import Tuple

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

# Allowed MIME types for image uploads
ALLOWED_CONTENT_TYPES: set[str] = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


def _client():
    """Return a fresh boto3 S3 client using settings credentials."""
    return boto3.client(
        "s3",
        region_name=settings.AWS_REGION,
        aws_access_key_id=settings.AWS_API_KEY,
        aws_secret_access_key=settings.AWS_SECRET_KEY,
    )


def generate_upload_url(
    object_key: str,
    content_type: str,
    expires: int | None = None,
) -> str:
    """Return a pre-signed S3 PUT URL for the given object key.

    The mobile app should:
    - PUT the raw binary to this URL
    - Set the Content-Type header to *content_type*
    - NOT include the Authorization header (this is a public PUT URL)
    """
    if expires is None:
        expires = settings.S3_UPLOAD_EXPIRES
    client = _client()
    url: str = client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.S3_BUCKET_NAME,
            "Key": object_key,
            "ContentType": content_type,
        },
        ExpiresIn=expires,
    )
    return url


def generate_download_url(
    object_key: str,
    expires: int | None = None,
) -> str:
    """Return a pre-signed S3 GET URL for the given object key."""
    if expires is None:
        expires = settings.S3_DOWNLOAD_EXPIRES
    client = _client()
    url: str = client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.S3_BUCKET_NAME,
            "Key": object_key,
        },
        ExpiresIn=expires,
    )
    return url


def make_object_key(prefix: str, file_name: str) -> Tuple[str, str]:
    """Generate a unique S3 object key and infer the content type.

    Returns (object_key, content_type).
    prefix example: "garages/abc-uuid"
    """
    ext = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    content_type = mimetypes.types_map.get(f".{ext}", "application/octet-stream")
    unique_name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
    return f"{prefix}/{unique_name}", content_type

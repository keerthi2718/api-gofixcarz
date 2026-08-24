"""Image upload pre-signed URL endpoint.

Flow:
  1. Mobile calls POST /api/v1/images/upload-url with file_name + content_type.
  2. Backend validates the request and returns a short-lived S3 pre-signed PUT URL
     and the object_key.
  3. Mobile PUTs the binary directly to S3 (no AWS credentials involved).
  4. Mobile calls the appropriate save endpoint (e.g. POST /api/v1/garage/logo)
     with the object_key to persist the reference.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException
from app.database.session import get_session
from app.dependencies.garage import CurrentGarage
from app.services.image_lifecycle_service import ImageLifecycleService
from app.utils.s3 import (
    ALLOWED_CONTENT_TYPES,
    generate_upload_url,
    make_object_key,
)
from app.schemas.response import APIResponse

router = APIRouter()
DBSession = Annotated[AsyncSession, Depends(get_session)]


class UploadUrlRequest(BaseModel):
    file_name: str
    content_type: str

    @field_validator("file_name")
    @classmethod
    def file_name_must_not_be_url(cls, v: str) -> str:
        if v.startswith("http://") or v.startswith("https://"):
            raise ValueError(
                "file_name must be a filename (e.g. 'logo.jpg'), not a URL. "
                "Upload the file binary directly to the upload_url returned by this endpoint."
            )
        return v


class UploadUrlResponse(BaseModel):
    upload_url: str
    object_key: str
    expires_in: int  # seconds


class OrphanCleanupRequest(BaseModel):
    older_than_hours: int = Field(default=24, ge=1, le=168)


@router.post("/upload-url", response_model=APIResponse[UploadUrlResponse])
async def get_upload_url(
    data: UploadUrlRequest,
    garage: CurrentGarage,
):
    """Generate a pre-signed S3 PUT URL for a garage image upload.

    The mobile app should:
    - PUT the raw image binary to `upload_url`
    - Set the `Content-Type` header to the value you sent here
    - NOT include the Authorization header on the S3 PUT request
    - After a successful upload, call the appropriate save endpoint with `object_key`

    Accepted types: JPEG, JPG, PNG, WebP — max 5 MB.
    """
    content_type = data.content_type.lower().strip()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise BadRequestException(
            f"Unsupported file type '{content_type}'. "
            f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
        )

    # Scope the object key to this garage
    prefix = f"garages/{garage.id}"
    object_key, _ = make_object_key(prefix, data.file_name)

    from app.core.config import settings
    expires = settings.S3_UPLOAD_EXPIRES
    upload_url = generate_upload_url(object_key, content_type, expires)

    return APIResponse.ok(
        data=UploadUrlResponse(
            upload_url=upload_url,
            object_key=object_key,
            expires_in=expires,
        ).model_dump(),
        message="Pre-signed upload URL generated",
    )


@router.delete("/{object_key:path}", response_model=APIResponse)
async def cancel_image_upload(
    garage: CurrentGarage,
    session: DBSession,
    object_key: str = Path(..., description="URL-encoded S3 object key"),
):
    """Delete an uploaded image that was never attached to a garage or job."""
    lifecycle = ImageLifecycleService(session)
    await lifecycle.cancel_upload(garage, object_key)
    return APIResponse.ok(message="Unattached image deleted")


@router.post("/cleanup", response_model=APIResponse[dict])
async def cleanup_orphaned_images(
    data: OrphanCleanupRequest,
    garage: CurrentGarage,
    session: DBSession,
):
    """Remove unreferenced images for the current garage after a safety delay."""
    lifecycle = ImageLifecycleService(session)
    deleted = await lifecycle.cleanup_orphans(garage, data.older_than_hours)
    return APIResponse.ok(
        data={"deleted_count": deleted, "older_than_hours": data.older_than_hours},
        message="Orphaned images cleaned up",
    )

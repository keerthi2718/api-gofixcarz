"""Private S3 images: bounded reads, actual decoding, metadata removal."""
import io
import re
from uuid import uuid4
from PIL import Image, ImageOps, UnidentifiedImageError
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy import select
from botocore.exceptions import BotoCoreError, ClientError
from app.core.config import settings
from app.core.customer_security import now
from app.models.customer_workspace import CustomerAttachment, CustomerResource
from app.services.customer_workspace_base import CustomerWorkspaceBase
from app.services.customer_otp_service import fail
from app.utils.s3 import _client

MAX_SIZE = 5 * 1024 * 1024
PURPOSES = {"PROFILE_PHOTO", "BOOKING_PHOTO", "SUPPORT_ATTACHMENT"}
FORMATS = {"JPEG": ("image/jpeg", "jpg"), "PNG": ("image/png", "png"), "WEBP": ("image/webp", "webp")}


def sanitize_image(contents, content_type):
    try:
        with Image.open(io.BytesIO(contents)) as image:
            if image.format not in FORMATS or FORMATS[image.format][0] != content_type:
                fail("ATTACHMENT_TYPE_UNSUPPORTED", 415)
            if image.width * image.height > 20_000_000 or getattr(image, "n_frames", 1) != 1:
                fail("ATTACHMENT_INVALID", 422)
            image.verify()
        with Image.open(io.BytesIO(contents)) as image:
            fmt = image.format
            image = ImageOps.exif_transpose(image)
            image = image.convert("RGB" if fmt == "JPEG" else "RGBA")
            output = io.BytesIO()
            image.save(output, format=fmt)
            if output.tell() > MAX_SIZE:
                fail("ATTACHMENT_TOO_LARGE", 413)
            return output.getvalue(), FORMATS[fmt]
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        fail("ATTACHMENT_INVALID", 422)


class CustomerAttachmentService(CustomerWorkspaceBase):
    @staticmethod
    def attachment_row(row):
        return {"id": row.id, "purpose": row.purpose, "filename": row.filename,
                "content_type": row.content_type, "size_bytes": row.size_bytes, "status": "READY",
                "download_path": f"/api/v1/customer-app/attachments/{row.id}/download"}

    async def attachment(self, identifier, purpose=None):
        row = (await self.db.execute(select(CustomerAttachment).where(
            CustomerAttachment.id == identifier, CustomerAttachment.customer_id == self.customer_id,
            CustomerAttachment.deleted_at.is_(None)))).scalar_one_or_none()
        if not row:
            fail("RESOURCE_NOT_FOUND", 404)
        if purpose and row.purpose != purpose:
            fail("ATTACHMENT_INVALID", 422)
        return row

    async def validate_attachments(self, identifiers, purpose):
        if len(set(identifiers)) != len(identifiers):
            fail("ATTACHMENT_INVALID", 422)
        for identifier in identifiers:
            await self.attachment(identifier, purpose)

    async def upload(self, file, purpose):
        if purpose not in PURPOSES:
            fail("ATTACHMENT_INVALID", 422)
        contents = await file.read(MAX_SIZE + 1)
        if len(contents) > MAX_SIZE:
            fail("ATTACHMENT_TOO_LARGE", 413)
        if not contents:
            fail("ATTACHMENT_INVALID", 422)
        clean, (content_type, extension) = await run_in_threadpool(sanitize_image, contents, file.content_type)
        identifier = uuid4()
        filename = re.sub(r"[^A-Za-z0-9_-]", "_", (file.filename or "image").rsplit(".", 1)[0])[:100]
        key = f"customers/{self.customer_id}/attachments/{identifier}.{extension}"
        try:
            await run_in_threadpool(lambda: _client().put_object(
                Bucket=settings.S3_BUCKET_NAME, Key=key, Body=clean, ContentType=content_type))
        except (BotoCoreError, ClientError):
            fail("ATTACHMENT_STORAGE_UNAVAILABLE", 503)
        row = CustomerAttachment(id=identifier, customer_id=self.customer_id, purpose=purpose,
                                 filename=f"{filename}.{extension}", content_type=content_type,
                                 size_bytes=len(clean), object_key=key)
        self.db.add(row)
        await self.db.flush()
        return self.attachment_row(row)

    async def download(self, identifier):
        row = await self.attachment(identifier)
        def fetch():
            result = _client().get_object(Bucket=settings.S3_BUCKET_NAME, Key=row.object_key)
            with result["Body"] as body:
                return body.read(MAX_SIZE + 1)
        try:
            contents = await run_in_threadpool(fetch)
        except (BotoCoreError, ClientError):
            fail("ATTACHMENT_STORAGE_UNAVAILABLE", 503)
        if len(contents) != row.size_bytes:
            fail("ATTACHMENT_STORAGE_UNAVAILABLE", 503)
        return Response(contents, media_type=row.content_type, headers={
            "Content-Disposition": f'inline; filename="{row.filename}"',
            "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"})

    async def remove_attachment(self, identifier):
        row = await self.attachment(identifier)
        resources = (await self.db.execute(select(CustomerResource).where(
            CustomerResource.customer_id == self.customer_id))).scalars().all()
        for resource in resources:
            payload = resource.payload
            if resource.kind == "QUOTE" and resource.status == "ACTIVE" and payload.get("expires_at", "") <= now().isoformat():
                continue
            if str(identifier) in payload.get("attachment_ids", []) or (
                resource.kind == "PHOTO" and resource.status == "ACTIVE" and
                payload.get("attachment_id") == str(identifier)
            ):
                fail("ATTACHMENT_IN_USE", 409)
        # Logical deletion is transactional. Never delete external bytes before
        # the DB commit: rollback could leave a live metadata row with no file.
        # Physical removal belongs to a separately approved retention worker.
        row.deleted_at = now()
        return {"id": row.id, "removed": True}

    async def set_photo(self, identifier):
        row = await self.attachment(identifier, "PROFILE_PHOTO")
        photo = (await self.db.execute(self.query("PHOTO"))).scalar_one_or_none()
        payload = {"attachment_id": str(identifier),
                   "download_path": self.attachment_row(row)["download_path"]}
        if photo:
            photo.payload, photo.status = payload, "ACTIVE"
        else:
            await self.add("PHOTO", payload, key="profile")
        return {"photo": payload}

    async def remove_photo(self):
        photo = (await self.db.execute(self.query("PHOTO"))).scalar_one_or_none()
        if photo:
            photo.status, photo.payload = "REMOVED", {}
        return {"removed": True}

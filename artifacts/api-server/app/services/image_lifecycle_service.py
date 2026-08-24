"""Validation and cleanup rules for garage-owned S3 image objects."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import BadRequestException, ConflictException
from app.models.garage import Garage
from app.models.job import Job
from app.utils.s3 import (
    delete_object,
    garage_prefix,
    is_garage_object_key,
    list_objects,
    object_exists,
)


def _photo_keys(value: object) -> set[str]:
    """Extract only string S3 keys from a JSONB photo list."""
    return {item for item in (value or []) if isinstance(item, str)}


class ImageLifecycleService:
    """Keep S3 objects scoped to a garage and remove unreferenced objects safely."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def validate_object_keys(
        self, garage_id: uuid.UUID, object_keys: list[str] | None
    ) -> list[str]:
        """Validate keys are unique, garage-owned, and already exist in S3."""
        keys = object_keys or []
        if len(keys) != len(set(keys)):
            raise BadRequestException("Each image can only be attached once.")

        for key in keys:
            if not is_garage_object_key(key, garage_id):
                raise BadRequestException("Image key is invalid or belongs to another garage.")
            if not await asyncio.to_thread(object_exists, key):
                raise BadRequestException("Image upload was not found in S3. Upload it before saving.")
        return keys

    async def referenced_keys(self, garage: Garage) -> set[str]:
        """Return every valid S3 key currently referenced by the garage or its jobs."""
        keys: set[str] = set()
        if garage.logo_url and is_garage_object_key(garage.logo_url, garage.id):
            keys.add(garage.logo_url)

        result = await self.session.execute(
            select(Job.photos).where(
                Job.garage_id == garage.id,
                Job.deleted_at.is_(None),
            )
        )
        for photos in result.scalars():
            keys.update(
                key for key in _photo_keys(photos)
                if is_garage_object_key(key, garage.id)
            )
        return keys

    async def delete_if_unreferenced(self, garage: Garage, object_key: str) -> bool:
        """Delete a garage-owned S3 object only when no active record references it."""
        if not is_garage_object_key(object_key, garage.id):
            return False
        if object_key in await self.referenced_keys(garage):
            return False

        try:
            await asyncio.to_thread(delete_object, object_key)
            return True
        except Exception:
            # A failed cleanup must not undo a successfully committed business update.
            logger.exception("Could not remove unreferenced S3 image object")
            return False

    async def cancel_upload(self, garage: Garage, object_key: str) -> None:
        """Remove one unreferenced upload for the current garage."""
        if not is_garage_object_key(object_key, garage.id):
            raise BadRequestException("Image key is invalid or belongs to another garage.")
        if object_key in await self.referenced_keys(garage):
            raise ConflictException("Cannot delete an image that is attached to a garage or job.")
        if not await asyncio.to_thread(object_exists, object_key):
            raise BadRequestException("Image upload was not found in S3.")
        await asyncio.to_thread(delete_object, object_key)

    async def cleanup_orphans(self, garage: Garage, older_than_hours: int = 24) -> int:
        """Delete unreferenced garage objects older than the requested age."""
        referenced = await self.referenced_keys(garage)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=older_than_hours)
        objects = await asyncio.to_thread(list_objects, garage_prefix(garage.id))
        stale_keys = [
            key for key, modified_at in objects
            if key not in referenced and modified_at <= cutoff
        ]

        deleted = 0
        for object_key in stale_keys:
            try:
                await asyncio.to_thread(delete_object, object_key)
                deleted += 1
            except Exception:
                logger.exception("Could not remove orphaned S3 image object")
        return deleted
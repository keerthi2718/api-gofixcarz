from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import BadRequestException, ConflictException
from app.services.image_lifecycle_service import ImageLifecycleService
from app.utils import s3


def test_garage_object_key_must_be_owned_by_current_garage():
    garage_id = uuid4()
    assert s3.is_garage_object_key(f"garages/{garage_id}/image.jpg", garage_id)
    assert not s3.is_garage_object_key("jobs/before_service/old-image.jpg", garage_id)
    assert not s3.is_garage_object_key(
        f"garages/{uuid4()}/image.jpg", garage_id
    )
    assert not s3.is_garage_object_key("https://example.com/image.jpg", garage_id)


@pytest.mark.asyncio
async def test_missing_upload_cannot_be_attached(monkeypatch):
    garage_id = uuid4()
    service = ImageLifecycleService(AsyncMock())
    monkeypatch.setattr(
        "app.services.image_lifecycle_service.object_exists", lambda _: False
    )

    with pytest.raises(BadRequestException, match="not found in S3"):
        await service.validate_object_keys(
            garage_id, [f"garages/{garage_id}/missing.jpg"]
        )


@pytest.mark.asyncio
async def test_other_garage_upload_cannot_be_attached(monkeypatch):
    garage_id = uuid4()
    service = ImageLifecycleService(AsyncMock())
    object_exists = AsyncMock()
    monkeypatch.setattr(
        "app.services.image_lifecycle_service.object_exists", object_exists
    )

    with pytest.raises(BadRequestException, match="belongs to another garage"):
        await service.validate_object_keys(
            garage_id, [f"garages/{uuid4()}/other-garage.jpg"]
        )
    object_exists.assert_not_called()


@pytest.mark.asyncio
async def test_attached_upload_cannot_be_cancelled(monkeypatch):
    garage_id = uuid4()
    key = f"garages/{garage_id}/attached.jpg"
    garage = type("Garage", (), {"id": garage_id})()
    service = ImageLifecycleService(AsyncMock())
    service.referenced_keys = AsyncMock(return_value={key})
    monkeypatch.setattr(
        "app.services.image_lifecycle_service.object_exists", lambda _: True
    )

    with pytest.raises(ConflictException):
        await service.cancel_upload(garage, key)


@pytest.mark.asyncio
async def test_cleanup_deletes_only_old_unreferenced_uploads(monkeypatch):
    garage_id = uuid4()
    referenced = f"garages/{garage_id}/attached.jpg"
    orphan = f"garages/{garage_id}/orphan.jpg"
    recent = f"garages/{garage_id}/recent.jpg"
    garage = type("Garage", (), {"id": garage_id})()
    service = ImageLifecycleService(AsyncMock())
    service.referenced_keys = AsyncMock(return_value={referenced})

    deleted: list[str] = []
    monkeypatch.setattr(
        "app.services.image_lifecycle_service.list_objects",
        lambda _: [
            (referenced, datetime.now(timezone.utc) - timedelta(days=2)),
            (orphan, datetime.now(timezone.utc) - timedelta(days=2)),
            (recent, datetime.now(timezone.utc) - timedelta(hours=1)),
        ],
    )
    monkeypatch.setattr(
        "app.services.image_lifecycle_service.delete_object",
        lambda key: deleted.append(key),
    )

    count = await service.cleanup_orphans(garage, older_than_hours=24)
    assert count == 1
    assert deleted == [orphan]
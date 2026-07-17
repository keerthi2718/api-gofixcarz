import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: uuid.UUID
    garage_id: uuid.UUID
    title: str
    message: str
    type: Optional[str] = None
    reference_id: Optional[uuid.UUID] = None
    read_at: Optional[datetime] = None
    is_read: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_with_read(cls, obj) -> "NotificationResponse":
        data = cls.model_validate(obj)
        data.is_read = obj.read_at is not None
        return data

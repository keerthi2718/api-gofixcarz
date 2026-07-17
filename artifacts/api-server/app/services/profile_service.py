import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictException, NotFoundException
from app.models.user import User
from app.schemas.profile import ProfileResponse, ProfileUpdate


class ProfileService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: uuid.UUID) -> ProfileResponse:
        user = await self.session.get(User, user_id)
        if not user:
            raise NotFoundException("User not found")
        return ProfileResponse.model_validate(user)

    async def update(self, user_id: uuid.UUID, data: ProfileUpdate) -> ProfileResponse:
        user = await self.session.get(User, user_id)
        if not user:
            raise NotFoundException("User not found")

        updates = data.model_dump(exclude_unset=True)

        # Check uniqueness for mobile/email
        if "mobile" in updates and updates["mobile"] != user.mobile:
            existing = (
                await self.session.execute(
                    select(User).where(User.mobile == updates["mobile"], User.id != user_id)
                )
            ).scalar_one_or_none()
            if existing:
                raise ConflictException("Mobile number is already in use")

        if "email" in updates and updates["email"] and updates["email"] != user.email:
            existing = (
                await self.session.execute(
                    select(User).where(User.email == updates["email"], User.id != user_id)
                )
            ).scalar_one_or_none()
            if existing:
                raise ConflictException("Email is already in use")

        for field, value in updates.items():
            setattr(user, field, value)
        user.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        await self.session.refresh(user)
        return ProfileResponse.model_validate(user)

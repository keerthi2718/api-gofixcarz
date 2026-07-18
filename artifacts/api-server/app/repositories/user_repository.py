import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.id == user_id, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_mobile(self, mobile: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.mobile == mobile, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.email == email, User.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        mobile: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        name: Optional[str] = None,
        email: Optional[str] = None,
        terms_accepted: bool = False,
    ) -> User:
        user = User(
            mobile=mobile,
            first_name=first_name,
            last_name=last_name,
            name=name,
            email=email,
            terms_accepted=terms_accepted,
        )
        self.session.add(user)
        await self.session.flush()
        await self.session.refresh(user)
        return user

    async def set_otp(self, user: User, otp: str, expires_at: datetime) -> User:
        user.otp = otp
        user.otp_expires_at = expires_at
        await self.session.flush()
        return user

    async def clear_otp(self, user: User) -> User:
        user.otp = None
        user.otp_expires_at = None
        await self.session.flush()
        return user

    async def update_profile(
        self,
        user: User,
        name: Optional[str] = None,
        email: Optional[str] = None,
    ) -> User:
        if name is not None:
            user.name = name
        if email is not None:
            user.email = email
        await self.session.flush()
        await self.session.refresh(user)
        return user

"""Delete expired credentials; retain used refresh hashes through session expiry."""
from datetime import timedelta

from sqlalchemy import delete, exists, select

from app.core.customer_security import now
from app.models.customer_auth import (
    CustomerAuthRateBucket, CustomerOTPChallenge, CustomerRefreshCredential,
    CustomerSession,
)


async def delete_expired_customer_credentials(session):
    cutoff = now() - timedelta(days=1)
    await session.execute(delete(CustomerOTPChallenge).where(
        CustomerOTPChallenge.expires_at <= cutoff,
    ))
    await session.execute(delete(CustomerAuthRateBucket).where(
        CustomerAuthRateBucket.window_start < int(cutoff.timestamp()),
    ))
    expired_ids = select(CustomerSession.id).where(
        CustomerSession.expires_at <= cutoff,
        ~exists().where(CustomerOTPChallenge.session_id == CustomerSession.id),
    )
    await session.execute(delete(CustomerRefreshCredential).where(
        CustomerRefreshCredential.session_id.in_(expired_ids),
    ))
    await session.execute(delete(CustomerSession).where(
        CustomerSession.id.in_(expired_ids),
    ))

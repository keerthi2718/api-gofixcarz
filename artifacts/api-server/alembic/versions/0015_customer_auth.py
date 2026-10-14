"""Add verified customer identity and dedicated OTP/session storage."""
from alembic import op

revision = "0015_customer_auth"
down_revision = "0014_admin_challenge_binding"
branch_labels = None
depends_on = None


def upgrade():
    from app.models.customer_auth import (
        CustomerIdentity, CustomerSession, CustomerRefreshCredential,
        CustomerOTPChallenge, CustomerAuthRateBucket,
    )
    for model in (
        CustomerIdentity, CustomerSession, CustomerRefreshCredential,
        CustomerOTPChallenge, CustomerAuthRateBucket,
    ):
        model.__table__.create(op.get_bind())


def downgrade():
    for name in (
        "customer_auth_rate_buckets", "customer_otp_challenges",
        "customer_refresh_credentials", "customer_sessions", "customer_identities",
    ):
        op.drop_table(name)

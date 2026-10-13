"""Separate administrator MFA, permissions and explicit scopes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011_admin_accounts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("admin_accounts", sa.Column("role_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("admin_accounts", sa.Column("garage_scope", postgresql.JSONB(), nullable=True))
    op.add_column("admin_accounts", sa.Column("mfa_required", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("admin_accounts", sa.Column("mfa_secret_encrypted", sa.String(512), nullable=True))
    op.add_column("admin_accounts", sa.Column("last_totp_counter", sa.Integer(), nullable=True))
    # Existing dedicated admins already have global privileges. No owner is promoted.
    op.execute("UPDATE admin_accounts SET role_ids = '[\"role_ceo\"]'::jsonb")
    op.add_column("admin_sessions", sa.Column("mfa_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("admin_sessions", sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("UPDATE admin_sessions SET family_id = id")
    op.alter_column("admin_sessions", "family_id", nullable=False)
    from app.models.admin_account import AdminMfaChallenge
    AdminMfaChallenge.__table__.create(op.get_bind())


def downgrade():
    op.drop_table("admin_mfa_challenges")
    for column in ["family_id", "mfa_verified_at"]:
        op.drop_column("admin_sessions", column)
    for column in ["last_totp_counter", "mfa_secret_encrypted", "mfa_required", "garage_scope", "role_ids"]:
        op.drop_column("admin_accounts", column)

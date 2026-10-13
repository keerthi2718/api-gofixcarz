"""Bind MFA proof to credential version; deny refresh families after concurrent replay."""
from alembic import op
import sqlalchemy as sa

revision = "0014_admin_challenge_binding"
down_revision = "0013_admin_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("admin_mfa_challenges", sa.Column("credential_version", sa.Integer(), nullable=False, server_default="1"))
    from app.models.admin_account import AdminRevokedFamily
    AdminRevokedFamily.__table__.create(op.get_bind())


def downgrade():
    op.drop_table("admin_revoked_session_families")
    op.drop_column("admin_mfa_challenges", "credential_version")

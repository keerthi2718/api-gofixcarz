"""Separate password-based admin accounts and revocable sessions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0011_admin_accounts"
down_revision = "0010_admin_role"
branch_labels = None
depends_on = None


def upgrade():
    uid = postgresql.UUID(as_uuid=True)
    op.create_table(
        "admin_accounts",
        sa.Column("id", uid, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("credential_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("email = lower(email)", name="ck_admin_accounts_email_normalized"),
    )
    op.create_table(
        "admin_sessions",
        sa.Column("id", uid, primary_key=True),
        sa.Column("admin_account_id", uid, sa.ForeignKey("admin_accounts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("credential_version", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_admin_sessions_admin_account_id", "admin_sessions", ["admin_account_id"])
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])
    op.alter_column("admin_audit_logs", "actor_id", nullable=True)
    op.add_column("admin_audit_logs", sa.Column(
        "admin_account_id", uid, sa.ForeignKey("admin_accounts.id", ondelete="RESTRICT"), nullable=True,
    ))
    op.create_index("ix_admin_audit_logs_admin_account_id", "admin_audit_logs", ["admin_account_id"])
    op.create_check_constraint("ck_admin_audit_logs_one_actor", "admin_audit_logs",
                               "(actor_id IS NULL) <> (admin_account_id IS NULL)")


def downgrade():
    # Audit history must be explicitly retained/exported before destructive rollback.
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM admin_audit_logs WHERE admin_account_id IS NOT NULL LIMIT 1")).first():
        raise RuntimeError("Refusing downgrade while dedicated admin audit history exists")
    op.drop_constraint("ck_admin_audit_logs_one_actor", "admin_audit_logs", type_="check")
    op.drop_index("ix_admin_audit_logs_admin_account_id", table_name="admin_audit_logs")
    op.drop_column("admin_audit_logs", "admin_account_id")
    op.alter_column("admin_audit_logs", "actor_id", nullable=False)
    op.drop_table("admin_sessions")
    op.drop_table("admin_accounts")

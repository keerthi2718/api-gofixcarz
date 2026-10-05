"""Add least-privilege user roles and admin audit history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0010_admin_role"
down_revision = "0009_sms_delivery_retention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing accounts stay garage owners. No account is automatically promoted.
    op.add_column("users", sa.Column("role", sa.String(20), nullable=False, server_default="garage_owner"))
    op.create_check_constraint("ck_users_role", "users", "role IN ('garage_owner', 'admin')")
    op.create_table(
        "admin_audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("details", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_admin_audit_logs_created_at", "admin_audit_logs", ["created_at"])
    op.create_index("ix_admin_audit_logs_actor_id", "admin_audit_logs", ["actor_id"])


def downgrade() -> None:
    op.drop_table("admin_audit_logs")
    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")

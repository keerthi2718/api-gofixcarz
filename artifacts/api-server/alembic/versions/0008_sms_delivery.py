"""Track redacted MSG91 delivery reports."""
from alembic import op
import sqlalchemy as sa

revision = "0008_sms_delivery"
down_revision = "0007_garage_logo_url"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sms_deliveries",
        sa.Column("request_id", sa.String(128), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("failure_category", sa.String(32)),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("reported_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('pending', 'delivered', 'failed')"),
    )


def downgrade() -> None:
    op.drop_table("sms_deliveries")
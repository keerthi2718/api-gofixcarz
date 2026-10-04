"""Index the immutable SMS delivery retention anchor."""
from alembic import op
import sqlalchemy as sa

revision = "0009_sms_delivery_retention"
down_revision = "0008_sms_delivery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_sms_deliveries_retention_started_at",
        "sms_deliveries",
        [sa.text("coalesce(accepted_at, created_at)")],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_sms_deliveries_retention_started_at", table_name="sms_deliveries"
    )
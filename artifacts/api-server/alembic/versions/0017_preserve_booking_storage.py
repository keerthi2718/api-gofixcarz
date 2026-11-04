"""Preserve existing production booking storage in the development schema.

Use the normal development Alembic flow. Replit Publish owns production
schema synchronization; this migration is not a build/startup hook.
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_preserve_booking_storage"
down_revision = "0016_customer_workspace"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "customer_app_booking_links", "slot_id",
        existing_type=sa.Uuid(), nullable=True,
    )
    for name in ("scheduled_start", "scheduled_end", "owner_accepted_at"):
        op.add_column("bookings", sa.Column(name, sa.DateTime(timezone=True), nullable=True))


def downgrade():
    raise RuntimeError(
        "Removing retained booking fields or requiring slots needs an explicit "
        "data-retention and legacy-booking review; no automatic destructive downgrade."
    )

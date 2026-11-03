"""Allow unscheduled customer bookings and owner-assigned schedules."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0017_optional_booking_slots"
down_revision = "0016_customer_workspace"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "customer_app_booking_links",
        "slot_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.add_column(
        "bookings",
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "bookings",
        sa.Column("scheduled_end", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    # Downgrade is intentionally blocked if any unscheduled booking links exist.
    bind = op.get_bind()
    if bind.execute(sa.text(
        "SELECT 1 FROM customer_app_booking_links WHERE slot_id IS NULL LIMIT 1"
    )).first():
        raise RuntimeError("Cannot require slot_id while unscheduled customer bookings exist")
    op.drop_column("bookings", "scheduled_end")
    op.drop_column("bookings", "scheduled_start")
    op.alter_column(
        "customer_app_booking_links",
        "slot_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

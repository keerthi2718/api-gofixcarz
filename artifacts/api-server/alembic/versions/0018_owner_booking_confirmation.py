"""Record owner acceptance separately from confirmation of an appointment."""
from alembic import op
import sqlalchemy as sa

revision = "0018_owner_booking_confirmation"
down_revision = "0017_optional_booking_slots"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "bookings",
        sa.Column("owner_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade():
    op.drop_column("bookings", "owner_accepted_at")

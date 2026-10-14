"""Add customer-owned vehicles, attachments and customer workflow storage."""
from alembic import op

revision = "0016_customer_workspace"
down_revision = "0015_customer_auth"
branch_labels = None
depends_on = None


def upgrade():
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'CANCELLED'")
        op.execute("ALTER TYPE booking_status ADD VALUE IF NOT EXISTS 'EXPIRED'")
    from app.models.customer_workspace import (
        CustomerVehicle, CustomerAttachment, CustomerResource, AppointmentSlot, CustomerBookingLink,
    )
    for model in (CustomerVehicle, CustomerAttachment, CustomerResource, AppointmentSlot, CustomerBookingLink):
        model.__table__.create(op.get_bind())


def downgrade():
    # PostgreSQL enum values intentionally remain; removing them requires a
    # separately reviewed data rewrite, never destructive implicit conversion.
    for name in ("customer_app_booking_links", "customer_app_slots", "customer_app_resources",
                 "customer_app_attachments", "customer_app_vehicles"):
        op.drop_table(name)

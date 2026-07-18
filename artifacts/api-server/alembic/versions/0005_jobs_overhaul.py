"""Jobs module overhaul

Revision ID: 0005_jobs_overhaul
Revises: 0004_separate_country_codes
Create Date: 2026-07-18 13:00:00.000000

Changes:
  - Adds READY to job_status enum
  - Makes jobs.customer_id and jobs.vehicle_id nullable (direct creation path)
  - Adds inline vehicle/customer columns on jobs: customer_name, customer_mobile,
    registration_number, brand, vehicle_model, fuel_type, odometer_km
  - Adds JSONB columns on jobs: photos, inspection, services, labour, billing
  - Adds job_seq (int) to garages for atomic per-garage sequential job IDs

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0005_jobs_overhaul"
down_revision: Union[str, None] = "0004_separate_country_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. Add READY to job_status enum ────────────────────────────────────────
    conn.execute(sa.text("ALTER TYPE job_status ADD VALUE IF NOT EXISTS 'READY'"))

    # ── 2. Make customer_id / vehicle_id nullable ───────────────────────────────
    op.alter_column("jobs", "customer_id", nullable=True)
    op.alter_column("jobs", "vehicle_id", nullable=True)

    # ── 3. Inline customer / vehicle fields ─────────────────────────────────────
    op.add_column("jobs", sa.Column("customer_name", sa.String(255), nullable=True))
    op.add_column("jobs", sa.Column("customer_mobile", sa.String(20), nullable=True))
    op.add_column("jobs", sa.Column("registration_number", sa.String(50), nullable=True))
    op.add_column("jobs", sa.Column("brand", sa.String(100), nullable=True))
    op.add_column("jobs", sa.Column("vehicle_model", sa.String(100), nullable=True))
    op.add_column("jobs", sa.Column("fuel_type", sa.String(50), nullable=True))
    op.add_column("jobs", sa.Column("odometer_km", sa.Integer, nullable=True))

    # Index registration_number for search
    op.create_index("ix_jobs_registration_number", "jobs", ["registration_number"])

    # ── 4. JSONB data columns ────────────────────────────────────────────────────
    op.add_column("jobs", sa.Column("photos", JSONB, nullable=True))
    op.add_column("jobs", sa.Column("inspection", JSONB, nullable=True))
    op.add_column("jobs", sa.Column("services", JSONB, nullable=True))
    op.add_column("jobs", sa.Column("labour", JSONB, nullable=True))
    op.add_column("jobs", sa.Column("billing", JSONB, nullable=True))

    # ── 5. Garage job sequence counter ──────────────────────────────────────────
    # job_seq holds the last-used sequence number so next = job_seq + 1.
    # Initialise from the current count of jobs per garage so existing garages
    # start their "JC-NNN" sequence at the right offset.
    op.add_column(
        "garages",
        sa.Column("job_seq", sa.Integer, nullable=False, server_default="0"),
    )
    # Backfill: set job_seq = count of non-deleted jobs for each garage
    conn.execute(
        sa.text(
            """
            UPDATE garages g
            SET job_seq = (
                SELECT COUNT(*)
                FROM jobs j
                WHERE j.garage_id = g.id AND j.deleted_at IS NULL
            )
            """
        )
    )


def downgrade() -> None:
    op.drop_column("garages", "job_seq")

    op.drop_column("jobs", "billing")
    op.drop_column("jobs", "labour")
    op.drop_column("jobs", "services")
    op.drop_column("jobs", "inspection")
    op.drop_column("jobs", "photos")

    op.drop_index("ix_jobs_registration_number", table_name="jobs")
    op.drop_column("jobs", "odometer_km")
    op.drop_column("jobs", "fuel_type")
    op.drop_column("jobs", "vehicle_model")
    op.drop_column("jobs", "brand")
    op.drop_column("jobs", "registration_number")
    op.drop_column("jobs", "customer_mobile")
    op.drop_column("jobs", "customer_name")

    op.alter_column("jobs", "vehicle_id", nullable=False)
    op.alter_column("jobs", "customer_id", nullable=False)

    # Note: PostgreSQL does not support removing enum values.
    # READY cannot be removed via downgrade without recreating the type.

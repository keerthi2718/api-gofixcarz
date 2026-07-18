"""Change job_number unique constraint to per-garage composite

Revision ID: 0006_jobs_job_number_per_garage
Revises: 0005_jobs_overhaul
Create Date: 2026-07-18 14:00:00.000000

The original schema made job_number globally unique across all garages.
The overhaul uses "JC-NNN" sequential numbers that are unique only within a
garage (garage A and garage B can both have JC-001).  This migration swaps
the global UNIQUE constraint for a composite UNIQUE(garage_id, job_number).

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006_jobs_job_number_per_garage"
down_revision: Union[str, None] = "0005_jobs_overhaul"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old single-column unique constraint created by 0001_initial_schema
    op.drop_constraint("jobs_job_number_key", "jobs", type_="unique")

    # Add per-garage composite unique constraint
    op.create_unique_constraint(
        "uq_jobs_garage_job_number", "jobs", ["garage_id", "job_number"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_jobs_garage_job_number", "jobs", type_="unique")
    op.create_unique_constraint("jobs_job_number_key", "jobs", ["job_number"])

"""Add logo_url to garages table.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_garage_logo_url"
down_revision = "0006_jobs_job_number_per_garage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "garages",
        sa.Column("logo_url", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("garages", "logo_url")

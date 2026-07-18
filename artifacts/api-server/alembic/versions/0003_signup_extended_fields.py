"""Add extended signup fields to users and garages

Revision ID: 0003_signup_extended_fields
Revises: 0002_add_refresh_tokens
Create Date: 2026-07-18 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from alembic import op

revision: str = "0003_signup_extended_fields"
down_revision: Union[str, None] = "0002_add_refresh_tokens"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users table ---
    op.add_column("users", sa.Column("first_name", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("last_name", sa.String(255), nullable=True))
    op.add_column(
        "users",
        sa.Column("terms_accepted", sa.Boolean(), nullable=False, server_default="false"),
    )

    # --- garages table ---
    op.add_column("garages", sa.Column("city", sa.String(100), nullable=True))
    op.add_column("garages", sa.Column("state", sa.String(100), nullable=True))
    op.add_column("garages", sa.Column("zipcode", sa.String(20), nullable=True))
    op.add_column("garages", sa.Column("country", sa.String(100), nullable=True))
    op.add_column(
        "garages",
        sa.Column("weeks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    # --- garages table ---
    op.drop_column("garages", "weeks")
    op.drop_column("garages", "country")
    op.drop_column("garages", "zipcode")
    op.drop_column("garages", "state")
    op.drop_column("garages", "city")

    # --- users table ---
    op.drop_column("users", "terms_accepted")
    op.drop_column("users", "last_name")
    op.drop_column("users", "first_name")

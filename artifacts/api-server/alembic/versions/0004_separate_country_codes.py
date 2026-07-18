"""Separate country_code from mobile in users table

Revision ID: 0004_separate_country_codes
Revises: 0003_signup_extended_fields
Create Date: 2026-07-18 12:00:00.000000

Migration strategy
------------------
The old API always stored mobile as the *concatenation* of country_code + 10-digit
mobile number (e.g. "919876543210" for country_code="91", mobile="9876543210").
This means the split is always deterministic:

    country_code = everything BEFORE the last 10 chars
    mobile       = last 10 chars

Rows that are already plain 10-digit (inserted via seed / before the country-code
requirement was enforced) are left untouched and assigned the default country_code
"91" (India).

No heuristics or prefix lookups are used — the split is purely positional.

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_separate_country_codes"
down_revision: Union[str, None] = "0003_signup_extended_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add country_code column (NOT NULL, server default = "91" for any rows that
    # the data migration does not touch explicitly).
    op.add_column(
        "users",
        sa.Column(
            "country_code",
            sa.String(10),
            nullable=False,
            server_default="91",
        ),
    )
    op.add_column(
        "users",
        sa.Column("country_code_2", sa.String(10), nullable=True),
    )

    # ── pre-migration sanity check ───────────────────────────────────────────
    # Rows with mobile shorter than 10 chars are invalid and should not exist
    # in a well-formed database. We log a count so operators can investigate.
    conn = op.get_bind()
    short = conn.execute(
        sa.text("SELECT COUNT(*) FROM users WHERE LENGTH(mobile) < 10")
    ).scalar()
    if short:
        import warnings
        warnings.warn(
            f"[0004_separate_country_codes] {short} row(s) have mobile shorter "
            "than 10 chars and will not be split. Investigate before re-running."
        )

    # ── deterministic split ──────────────────────────────────────────────────
    # For every row where mobile is longer than 10 digits:
    #   country_code ← first (N-10) chars
    #   mobile       ← last 10 chars
    #
    # The old system always concatenated country_code + 10-digit mobile, so this
    # is always the correct inverse operation regardless of which country code was
    # used.  No prefix lookup tables or heuristics are required.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET
                country_code = LEFT(mobile, LENGTH(mobile) - 10),
                mobile       = RIGHT(mobile, 10)
            WHERE LENGTH(mobile) > 10
            """
        )
    )

    # ── post-migration verification ──────────────────────────────────────────
    # After the split, every mobile must be exactly 10 digits and every
    # country_code must be 1–4 digits.  Log a warning if any row fails.
    bad_mobile = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM users WHERE LENGTH(mobile) != 10 AND deleted_at IS NULL"
        )
    ).scalar()
    bad_cc = conn.execute(
        sa.text(
            "SELECT COUNT(*) FROM users "
            "WHERE (LENGTH(country_code) < 1 OR LENGTH(country_code) > 4) "
            "AND deleted_at IS NULL"
        )
    ).scalar()
    if bad_mobile or bad_cc:
        import warnings
        warnings.warn(
            f"[0004_separate_country_codes] Post-migration check: "
            f"{bad_mobile} row(s) with non-10-digit mobile, "
            f"{bad_cc} row(s) with invalid country_code. "
            "Review these rows before deploying."
        )


def downgrade() -> None:
    # Merge country_code back into mobile before dropping the column.
    # Only re-merges rows where mobile is exactly 10 digits (the normal state
    # after upgrade); rows in abnormal states are left as-is.
    op.execute(
        sa.text(
            """
            UPDATE users
            SET mobile = country_code || mobile
            WHERE LENGTH(mobile) = 10
            """
        )
    )
    op.drop_column("users", "country_code_2")
    op.drop_column("users", "country_code")

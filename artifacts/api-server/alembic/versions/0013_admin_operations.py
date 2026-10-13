"""Persist admin domain sources and workflow resources, development rollout."""
from alembic import op
import sqlalchemy as sa

revision = "0013_admin_operations"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("garages", sa.Column("operational_status", sa.String(20), nullable=False, server_default="ACTIVE"))
    op.add_column("garages", sa.Column("verification_status", sa.String(20), nullable=False, server_default="UNVERIFIED"))
    op.add_column("garages", sa.Column("admin_version", sa.Integer(), nullable=False, server_default="1"))
    from app.models.admin_operations import CustomerAccount, AccountGarage, SourceRecord, SupportMessage, AdminResource
    for model in (CustomerAccount, AccountGarage, SourceRecord, SupportMessage, AdminResource):
        model.__table__.create(op.get_bind())


def downgrade():
    for table in ("admin_resources", "support_messages", "admin_source_records",
                  "customer_account_garages", "customer_accounts"):
        op.drop_table(table)
    for column in ("admin_version", "verification_status", "operational_status"):
        op.drop_column("garages", column)

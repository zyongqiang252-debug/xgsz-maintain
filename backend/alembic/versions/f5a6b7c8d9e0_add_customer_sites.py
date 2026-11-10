"""customer sites + work order site snapshot

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_sites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("address", sa.String(300)),
        sa.Column("contact_name", sa.String(100)),
        sa.Column("contact_phone", sa.String(20)),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("remark", sa.String(500)),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_customer_sites_customer_id", "customer_sites", ["customer_id"])
    op.add_column("work_orders", sa.Column("customer_site_id", sa.Integer(), sa.ForeignKey("customer_sites.id"), nullable=True))
    op.add_column("work_orders", sa.Column("customer_site_name", sa.String(100), nullable=True))
    op.add_column("work_orders", sa.Column("customer_address", sa.String(300), nullable=True))


def downgrade():
    op.drop_column("work_orders", "customer_address")
    op.drop_column("work_orders", "customer_site_name")
    op.drop_column("work_orders", "customer_site_id")
    op.drop_table("customer_sites")

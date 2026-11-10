"""add customers / customer_devices / work_orders.customer_id

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "a8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("company", sa.String(200)),
        sa.Column("remark", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_customers_phone", "customers", ["phone"], unique=True)

    op.create_table(
        "customer_devices",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("devices.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("device_id", name="uq_customer_device"),
    )
    op.create_index("ix_customer_devices_customer_id", "customer_devices", ["customer_id"])
    op.create_index("ix_customer_devices_device_id", "customer_devices", ["device_id"])

    op.add_column("work_orders", sa.Column("customer_id", sa.Integer(), sa.ForeignKey("customers.id"), nullable=True))
    op.add_column("work_orders", sa.Column("customer_name", sa.String(100), nullable=True))
    op.create_index("ix_work_orders_customer_id", "work_orders", ["customer_id"])


def downgrade():
    op.drop_index("ix_work_orders_customer_id", table_name="work_orders")
    op.drop_column("work_orders", "customer_name")
    op.drop_column("work_orders", "customer_id")
    op.drop_table("customer_devices")
    op.drop_table("customers")

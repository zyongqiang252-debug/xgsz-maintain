"""add customer snapshot fields to work_orders

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "c0d1e2f3a4b5"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("work_orders", sa.Column("customer_company", sa.String(200), nullable=True))
    op.add_column("work_orders", sa.Column("customer_phone", sa.String(20), nullable=True))
    op.add_column("work_orders", sa.Column("customer_contact_name", sa.String(100), nullable=True))
    op.add_column("work_orders", sa.Column("customer_contact_phone", sa.String(20), nullable=True))


def downgrade():
    for col in ("customer_contact_phone", "customer_contact_name", "customer_phone", "customer_company"):
        op.drop_column("work_orders", col)

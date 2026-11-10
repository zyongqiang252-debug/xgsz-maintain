"""work order: hold, RMA tracking, customer acceptance, delivery fields

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None

COLUMNS = [
    ("is_on_hold", sa.Boolean(), {"nullable": False, "server_default": sa.text("false")}),
    ("hold_reason", sa.String(20), {"nullable": True}),
    ("hold_remark", sa.Text(), {"nullable": True}),
    ("hold_started_at", sa.DateTime(), {"nullable": True}),
    ("hold_total_minutes", sa.Integer(), {"nullable": False, "server_default": "0"}),
    ("rma_vendor", sa.String(200), {"nullable": True}),
    ("rma_no", sa.String(100), {"nullable": True}),
    ("rma_status", sa.String(20), {"nullable": True}),
    ("rma_shipped_at", sa.DateTime(), {"nullable": True}),
    ("rma_vendor_received_at", sa.DateTime(), {"nullable": True}),
    ("rma_returned_at", sa.DateTime(), {"nullable": True}),
    ("rma_replacement_sn", sa.String(100), {"nullable": True}),
    ("rma_remark", sa.Text(), {"nullable": True}),
    ("customer_accept_status", sa.String(20), {"nullable": True}),
    ("customer_accept_at", sa.DateTime(), {"nullable": True}),
    ("customer_accept_by", sa.String(100), {"nullable": True}),
    ("customer_accept_remark", sa.Text(), {"nullable": True}),
    ("project_name", sa.String(200), {"nullable": True}),
    ("delivery_batch", sa.String(100), {"nullable": True}),
    ("rack_location", sa.String(200), {"nullable": True}),
    ("power_on_at", sa.DateTime(), {"nullable": True}),
    ("warranty_start", sa.DateTime(), {"nullable": True}),
    ("warranty_end", sa.DateTime(), {"nullable": True}),
]


def upgrade():
    for name, typ, kw in COLUMNS:
        op.add_column("work_orders", sa.Column(name, typ, **kw))
    op.create_index("ix_work_orders_is_on_hold", "work_orders", ["is_on_hold"])


def downgrade():
    op.drop_index("ix_work_orders_is_on_hold", table_name="work_orders")
    for name, _typ, _kw in reversed(COLUMNS):
        op.drop_column("work_orders", name)

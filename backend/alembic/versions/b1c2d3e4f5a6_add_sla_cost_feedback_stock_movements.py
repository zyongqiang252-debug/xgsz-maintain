"""add sla / feedback / cost to work_orders, create stock_movements

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f7
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa

revision = "b1c2d3e4f5a6"
down_revision = "a1b2c3d4e5f7"
branch_labels = None
depends_on = None


def upgrade():
    # 1) 工单：SLA / 回访 / 成本
    op.add_column("work_orders", sa.Column("response_due_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("work_orders", sa.Column("resolve_due_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("work_orders", sa.Column("first_response_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("work_orders", sa.Column("resolved_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("work_orders", sa.Column("sla_status", sa.String(16), nullable=True))
    op.add_column("work_orders", sa.Column("satisfaction_score", sa.Integer(), nullable=True))
    op.add_column("work_orders", sa.Column("satisfaction_comment", sa.Text(), nullable=True))
    op.add_column("work_orders", sa.Column("feedback_at", sa.TIMESTAMP(), nullable=True))
    op.add_column("work_orders", sa.Column("labor_cost", sa.Float(), nullable=True))
    op.add_column("work_orders", sa.Column("parts_cost", sa.Float(), nullable=True))
    op.add_column("work_orders", sa.Column("total_cost", sa.Float(), nullable=True))
    op.create_index("ix_work_orders_sla_status", "work_orders", ["sla_status"])

    # 2) 备件出入库流水
    op.create_table(
        "stock_movements",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("spare_parts.id"), nullable=False),
        sa.Column("part_code", sa.String(50)),
        sa.Column("part_name", sa.String(200)),
        sa.Column("movement_type", sa.String(16), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("before_qty", sa.Float()),
        sa.Column("after_qty", sa.Float()),
        sa.Column("unit_price", sa.Float(), default=0.0),
        sa.Column("amount", sa.Float(), default=0.0),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id")),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("operator_name", sa.String(100)),
        sa.Column("remark", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
    )
    op.create_index("ix_stock_movements_part_id", "stock_movements", ["part_id"])
    op.create_index("ix_stock_movements_part_code", "stock_movements", ["part_code"])
    op.create_index("ix_stock_movements_type", "stock_movements", ["movement_type"])
    op.create_index("ix_stock_movements_work_order_id", "stock_movements", ["work_order_id"])


def downgrade():
    op.drop_table("stock_movements")
    op.drop_index("ix_work_orders_sla_status", table_name="work_orders")
    for col in ("total_cost", "parts_cost", "labor_cost", "feedback_at", "satisfaction_comment",
                "satisfaction_score", "sla_status", "resolved_at", "first_response_at",
                "resolve_due_at", "response_due_at"):
        op.drop_column("work_orders", col)

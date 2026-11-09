"""add spare part requisitions (领用申请/审批)

Revision ID: c4d5e6f7a8b9
Revises: e2f3a4b5c6d7
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

revision = "c4d5e6f7a8b9"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "spare_part_requisitions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("part_id", sa.Integer(), sa.ForeignKey("spare_parts.id"), nullable=False),
        sa.Column("part_code", sa.String(50)),
        sa.Column("part_name", sa.String(200)),
        sa.Column("quantity", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(20), server_default="个"),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id")),
        sa.Column("reason", sa.Text()),
        sa.Column("status", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("applicant_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("applicant_name", sa.String(100)),
        sa.Column("approver_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("approver_name", sa.String(100)),
        sa.Column("approved_at", sa.DateTime()),
        sa.Column("reject_reason", sa.Text()),
        sa.Column("movement_id", sa.Integer(), sa.ForeignKey("stock_movements.id")),
        sa.Column("issued_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_spare_part_requisitions_part_id", "spare_part_requisitions", ["part_id"])
    op.create_index("ix_spare_part_requisitions_part_code", "spare_part_requisitions", ["part_code"])
    op.create_index("ix_spare_part_requisitions_work_order_id", "spare_part_requisitions", ["work_order_id"])
    op.create_index("ix_spare_part_requisitions_status", "spare_part_requisitions", ["status"])
    op.create_index("ix_spare_part_requisitions_applicant_id", "spare_part_requisitions", ["applicant_id"])


def downgrade():
    op.drop_table("spare_part_requisitions")

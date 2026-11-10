"""add work_order_edit_logs (已归档工单管理员修改审计)

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "work_order_edit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("editor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("editor_name", sa.String(100)),
        sa.Column("status_at_edit", sa.String(16)),
        sa.Column("changes", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_work_order_edit_logs_work_order_id", "work_order_edit_logs", ["work_order_id"])


def downgrade():
    op.drop_table("work_order_edit_logs")

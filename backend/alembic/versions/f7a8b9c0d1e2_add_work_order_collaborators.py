"""add work_order_collaborators (多人协作：主责 + 协作人)

Revision ID: f7a8b9c0d1e2
Revises: d5e6f7a8b9c0
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "f7a8b9c0d1e2"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "work_order_collaborators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_order_id", sa.Integer(), sa.ForeignKey("work_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("work_order_id", "user_id", name="uq_work_order_collaborator"),
    )
    op.create_index("ix_work_order_collaborators_work_order_id", "work_order_collaborators", ["work_order_id"])
    op.create_index("ix_work_order_collaborators_user_id", "work_order_collaborators", ["user_id"])


def downgrade():
    op.drop_table("work_order_collaborators")

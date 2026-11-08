"""add login_logs table

Revision ID: b2c3d4e5f6a7
Revises: b1c2d3e4f5a6
Create Date: 2026-11-08
"""
from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "login_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id")),
        sa.Column("username", sa.String(100)),
        sa.Column("real_name", sa.String(100)),
        sa.Column("login_type", sa.String(20), server_default="password"),
        sa.Column("success", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("reason", sa.String(200)),
        sa.Column("ip", sa.String(64)),
        sa.Column("user_agent", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("now()")),
    )
    op.create_index("ix_login_logs_user_id", "login_logs", ["user_id"])
    op.create_index("ix_login_logs_username", "login_logs", ["username"])
    op.create_index("ix_login_logs_success", "login_logs", ["success"])


def downgrade():
    op.drop_table("login_logs")

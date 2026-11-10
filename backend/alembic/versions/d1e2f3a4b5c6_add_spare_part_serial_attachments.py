"""add serial_no / attachments to spare_parts and stock_movements

Revision ID: d1e2f3a4b5c6
Revises: e7f8a9b0c1d2
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("spare_parts", sa.Column("serial_no", sa.String(500), nullable=True))
    op.add_column("spare_parts", sa.Column("attachments", sa.JSON(), nullable=True))
    op.add_column("stock_movements", sa.Column("serial_no", sa.String(500), nullable=True))
    op.add_column("stock_movements", sa.Column("attachments", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("stock_movements", "attachments")
    op.drop_column("stock_movements", "serial_no")
    op.drop_column("spare_parts", "attachments")
    op.drop_column("spare_parts", "serial_no")

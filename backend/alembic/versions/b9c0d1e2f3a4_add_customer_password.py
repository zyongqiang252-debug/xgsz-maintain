"""add customers.password_hash

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "b9c0d1e2f3a4"
down_revision = "a8b9c0d1e2f3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customers", sa.Column("password_hash", sa.String(255), nullable=True))


def downgrade():
    op.drop_column("customers", "password_hash")

"""导入批次增加来源类型，导入记录增加 Excel 行号

Revision ID: a1b2c3d4e5f7
Revises: 86657f16ee0a
Create Date: 2026-11-04 22:45:00
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f7"
down_revision = "86657f16ee0a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE work_order_import_batches ADD COLUMN IF NOT EXISTS source VARCHAR(20) NOT NULL DEFAULT 'PDF'")
    op.execute("ALTER TABLE work_order_import_items ADD COLUMN IF NOT EXISTS row_no INTEGER")
    op.execute("CREATE INDEX IF NOT EXISTS ix_woi_batch_row ON work_order_import_items (batch_id, row_no)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_woi_batch_row")
    op.execute("ALTER TABLE work_order_import_items DROP COLUMN IF EXISTS row_no")
    op.execute("ALTER TABLE work_order_import_batches DROP COLUMN IF EXISTS source")

"""add_workorder_status_values

Revision ID: b7c4d8e1f2a3
Revises: a43b0de36259
Create Date: 2026-07-27 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7c4d8e1f2a3'
down_revision: Union[str, None] = 'a43b0de36259'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # 用 IF NOT EXISTS 保证幂等：原写法靠 try/except 吞异常，
    # 但在 PostgreSQL 中一条语句失败会让整个事务进入 aborted 状态，
    # 后续 ALTER 与 alembic_version 更新都会连续失败。
    new_values = [
        'DRAFT', 'ASSIGNED', 'ACCEPTED', 'ARRIVED', 'INSPECTING',
        'IN_PROGRESS', 'COMPLETED', 'ARCHIVING',
        'STANDARDIZED', 'CLASSIFIED', 'APPROVED', 'ARCHIVED',
    ]
    for val in new_values:
        conn.execute(sa.text(f"ALTER TYPE workorderstatus ADD VALUE IF NOT EXISTS '{val}'"))


def downgrade() -> None:
    pass

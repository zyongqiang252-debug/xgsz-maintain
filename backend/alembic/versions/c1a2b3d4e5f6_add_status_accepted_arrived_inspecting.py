"""add_status_accepted_arrived_inspecting

Revision ID: c1a2b3d4e5f6
Revises: b3c2d1e5f7a4
Create Date: 2026-07-31 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1a2b3d4e5f6'
down_revision: Union[str, None] = 'b3c2d1e5f7a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    # 幂等写法：不能用 try/except 吞异常，
    # PostgreSQL 中语句失败会让事务进入 aborted 状态，后续全部失败并整体回滚
    new_values = ['ACCEPTED', 'ARRIVED', 'INSPECTING']
    for val in new_values:
        conn.execute(sa.text(f"ALTER TYPE workorderstatus ADD VALUE IF NOT EXISTS '{val}'"))


def downgrade() -> None:
    # 从 enum 移除值通常无法直接操作（Postgres 限制），此处留空
    pass

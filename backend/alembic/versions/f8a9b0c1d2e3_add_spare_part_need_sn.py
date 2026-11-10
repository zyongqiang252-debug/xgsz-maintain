"""add spare_parts.need_sn（是否需要按 SN 一物一码追溯）

Revision ID: f8a9b0c1d2e3
Revises: d1e2f3a4b5c6
Create Date: 2026-11-10

勾上 need_sn 的备件（GPU 卡/内存/光模块…）在入库时必须逐件填 SN，
数量与 SN 个数不一致直接拦；耗材类保持不勾，入库照旧只填数量。

回填规则：已经录过 serial_no 的备件自动勾上（说明本来就在按 SN 管）。
"""
from alembic import op
import sqlalchemy as sa

revision = "f8a9b0c1d2e3"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("spare_parts", sa.Column(
        "need_sn", sa.Boolean(), nullable=False, server_default=sa.text("false"),
    ))
    op.execute(
        "UPDATE spare_parts SET need_sn = true "
        "WHERE serial_no IS NOT NULL AND btrim(serial_no) <> ''"
    )


def downgrade():
    op.drop_column("spare_parts", "need_sn")

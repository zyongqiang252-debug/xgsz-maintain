"""stock_movements 增加来源单据与仓库维度

Revision ID: c7d8e9f0a1b2
Revises: f8a9b0c1d2e3
Create Date: 2026-11-10

为「流水是唯一事实源」补两个维度：
  source_type/source_id —— 这笔变动是哪张单据引起的（期初/领用单/盘点单），
                            唯一索引保证同一张单据对同一个件只记一次，重复提交不重复扣。
  warehouse_id          —— 仓库维度，多仓时能分仓对账；历史数据为 NULL 视为未分仓。
手工出入库（无单据）保持 source 为 NULL，不受唯一索引限制（Postgres 中 NULL 互不相等）。
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d8e9f0a1b2"
down_revision = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "stock_movements",
        sa.Column("source_type", sa.String(24), nullable=True,
                  comment="来源单据类型：OPENING / REQUISITION / STOCKTAKE"),
    )
    op.add_column(
        "stock_movements",
        sa.Column("source_id", sa.Integer(), nullable=True, comment="来源单据 ID"),
    )
    op.add_column(
        "stock_movements",
        sa.Column("warehouse_id", sa.Integer(), nullable=True, comment="仓库 ID"),
    )
    op.create_index(
        "uq_stock_movement_source",
        "stock_movements",
        ["source_type", "source_id", "part_id", "movement_type"],
        unique=True,
    )
    op.create_index("ix_stock_movements_warehouse_id", "stock_movements", ["warehouse_id"])


def downgrade():
    op.drop_index("ix_stock_movements_warehouse_id", table_name="stock_movements")
    op.drop_index("uq_stock_movement_source", table_name="stock_movements")
    op.drop_column("stock_movements", "warehouse_id")
    op.drop_column("stock_movements", "source_id")
    op.drop_column("stock_movements", "source_type")

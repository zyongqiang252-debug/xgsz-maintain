r"""工单增加 GPU 维修专有字段

新增（work_orders）：
  gpu_index          故障 GPU 序号（如 GPU3 / 0-7）
  fault_device_sn    故障部件序列号（卡 SN / 内存条 SN 等）
  service_mode       服务方式 REMOTE(远程) / SITE(现场) / RMA(返厂)
  need_rma           是否需要返厂

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""
from alembic import op
import sqlalchemy as sa

revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("work_orders", sa.Column("gpu_index", sa.String(50), nullable=True,
                                          comment="故障 GPU 序号，如 GPU3 / 0-7"))
    op.add_column("work_orders", sa.Column("fault_device_sn", sa.String(100), nullable=True,
                                          comment="故障部件序列号（GPU 卡/内存条等）"))
    op.add_column("work_orders", sa.Column("service_mode", sa.String(20), nullable=True,
                                          comment="服务方式 REMOTE/SITE/RMA"))
    op.add_column("work_orders", sa.Column("need_rma", sa.Boolean(), nullable=True,
                                          comment="是否需要返厂维修"))
    op.create_index("ix_work_orders_service_mode", "work_orders", ["service_mode"])


def downgrade():
    op.drop_index("ix_work_orders_service_mode", table_name="work_orders")
    for col in ("need_rma", "service_mode", "fault_device_sn", "gpu_index"):
        op.drop_column("work_orders", col)

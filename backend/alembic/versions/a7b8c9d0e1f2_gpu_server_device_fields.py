r"""GPU 服务器维修：设备表扩展字段

新增（devices）：
  serial_no / room / rack_no / rack_unit / bmc_ip / business_ip
  gpu_model / gpu_count / gpu_serial / driver_version / cuda_version / firmware_version
  cpu_model / memory_gb / os_version / project

Revision ID: a7b8c9d0e1f2
Revises: f2a3b4c5d6e7
"""
from alembic import op
import sqlalchemy as sa

revision = "a7b8c9d0e1f2"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None

COLS = [
    ("serial_no", sa.String(100), "设备序列号 SN"),
    ("room", sa.String(50), "机房"),
    ("rack_no", sa.String(50), "机柜号"),
    ("rack_unit", sa.String(50), "U 位（如 U12-U19）"),
    ("bmc_ip", sa.String(50), "BMC/带外管理 IP"),
    ("business_ip", sa.String(50), "业务网 IP"),
    ("gpu_model", sa.String(100), "GPU 型号（如 H100 80G SXM5）"),
    ("gpu_count", sa.Integer(), "GPU 数量"),
    ("gpu_serial", sa.Text(), "各卡序列号（换行分隔）"),
    ("driver_version", sa.String(50), "驱动版本"),
    ("cuda_version", sa.String(50), "CUDA 版本"),
    ("firmware_version", sa.String(100), "固件/BMC 版本"),
    ("cpu_model", sa.String(100), "CPU 型号"),
    ("memory_gb", sa.Integer(), "内存容量 GB"),
    ("os_version", sa.String(100), "操作系统版本"),
    ("project", sa.String(100), "所属项目/客户"),
]


def upgrade():
    for name, typ, comment in COLS:
        op.add_column("devices", sa.Column(name, typ, nullable=True, comment=comment))
    op.create_index("ix_devices_serial_no", "devices", ["serial_no"])
    op.create_index("ix_devices_room", "devices", ["room"])


def downgrade():
    op.drop_index("ix_devices_room", table_name="devices")
    op.drop_index("ix_devices_serial_no", table_name="devices")
    for name, _typ, _c in reversed(COLS):
        op.drop_column("devices", name)

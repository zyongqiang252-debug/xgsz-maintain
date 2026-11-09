r"""统一告警级别：设备告警级别 + 通知级别

- devices.alert_level        P0~P3，取故障标签里最高级别（写时维护，便于筛选排序）
- notifications.level        P0~P3，默认 P2

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
"""
from alembic import op
import sqlalchemy as sa

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("devices", sa.Column("alert_level", sa.String(8), nullable=True,
                                       comment="告警级别 P0/P1/P2/P3（取故障标签最高级别）"))
    op.create_index("ix_devices_alert_level", "devices", ["alert_level"])

    op.add_column("notifications", sa.Column("level", sa.String(8), nullable=False,
                                             server_default="P2", comment="告警级别 P0~P3"))
    op.create_index("ix_notifications_level", "notifications", ["level"])

    # 历史数据：通知按类型兜底
    op.execute("UPDATE notifications SET level='P3' WHERE type='system'")
    op.execute("UPDATE notifications SET level='P1' WHERE title LIKE '%预警%' OR title LIKE '%库存%'")


def downgrade():
    op.drop_index("ix_notifications_level", table_name="notifications")
    op.drop_column("notifications", "level")
    op.drop_index("ix_devices_alert_level", table_name="devices")
    op.drop_column("devices", "alert_level")

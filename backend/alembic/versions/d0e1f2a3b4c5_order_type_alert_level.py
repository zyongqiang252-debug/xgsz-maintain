r"""工单增加「工单类型」与「告警级别」两个可筛选字段

- work_orders.order_type   REPAIR(报修) / MAINTENANCE(保养) / INSPECTION(点检) / IMPORT(导入)
- work_orders.alert_level  P0~P3，由优先级推导，SLA 超时升 P0（落库才能筛选/排序）

回填：
- order_type：工单号 PM- 开头→MAINTENANCE，INSP- 开头→INSPECTION，
  fault_category 含「保养/点检」的也归类，其余→REPAIR
- alert_level：按 priority 映射（CRITICAL→P0、HIGH→P1、MEDIUM→P2、LOW→P3）

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""
from alembic import op
import sqlalchemy as sa

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("work_orders", sa.Column("order_type", sa.String(20), nullable=True,
                                           comment="工单类型 REPAIR/MAINTENANCE/INSPECTION/IMPORT"))
    op.create_index("ix_work_orders_order_type", "work_orders", ["order_type"])

    op.add_column("work_orders", sa.Column("alert_level", sa.String(8), nullable=True,
                                           comment="告警级别 P0~P3（优先级推导，SLA 超时升 P0）"))
    op.create_index("ix_work_orders_alert_level", "work_orders", ["alert_level"])

    # 回填工单类型
    op.execute("UPDATE work_orders SET order_type='MAINTENANCE' WHERE work_order_no LIKE 'PM-%'")
    op.execute("UPDATE work_orders SET order_type='INSPECTION' WHERE work_order_no LIKE 'INSP-%'")
    op.execute("""UPDATE work_orders SET order_type='MAINTENANCE'
                  WHERE order_type IS NULL AND fault_category LIKE '%保养%'""")
    op.execute("""UPDATE work_orders SET order_type='INSPECTION'
                  WHERE order_type IS NULL AND fault_category LIKE '%点检%'""")
    op.execute("UPDATE work_orders SET order_type='REPAIR' WHERE order_type IS NULL")

    # 回填告警级别
    op.execute("""UPDATE work_orders SET alert_level =
                    CASE UPPER(COALESCE(priority,'MEDIUM'))
                      WHEN 'CRITICAL' THEN 'P0' WHEN 'HIGH' THEN 'P1'
                      WHEN 'LOW' THEN 'P3' ELSE 'P2' END""")
    op.execute("UPDATE work_orders SET alert_level='P0' WHERE sla_status='OVERDUE'")


def downgrade():
    op.drop_index("ix_work_orders_alert_level", table_name="work_orders")
    op.drop_column("work_orders", "alert_level")
    op.drop_index("ix_work_orders_order_type", table_name="work_orders")
    op.drop_column("work_orders", "order_type")

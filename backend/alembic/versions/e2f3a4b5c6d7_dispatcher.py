r"""工单记录分配人（派工人）

- work_orders.dispatcher_id  派工/改派操作人（users.id）
- work_orders.dispatched_at  最近一次派工时间

回填：从进度日志里取「-> 已派单(ASSIGNED)」这条记录的操作人；
      没有日志但有维修员的，退化为创建人。
"""
from alembic import op
import sqlalchemy as sa

revision = "e2f3a4b5c6d7"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("work_orders", sa.Column("dispatcher_id", sa.Integer(), nullable=True,
                                           comment="分配人（派工操作人）users.id"))
    op.add_column("work_orders", sa.Column("dispatched_at", sa.DateTime(), nullable=True,
                                           comment="最近一次派工时间"))
    op.create_index("ix_work_orders_dispatcher_id", "work_orders", ["dispatcher_id"])

    # 回填：取进度日志中第一次「到 ASSIGNED」的操作人
    op.execute("""
        UPDATE work_orders w
        SET dispatcher_id = l.operator_id,
            dispatched_at = l.created_at
        FROM (
            SELECT DISTINCT ON (work_order_id) work_order_id, operator_id, created_at
            FROM work_order_progress_logs
            WHERE to_status = 'ASSIGNED' AND operator_id IS NOT NULL
            ORDER BY work_order_id, created_at ASC
        ) l
        WHERE l.work_order_id = w.id
    """)
    # 兜底：有维修员但没派工日志的，用创建人
    op.execute("""
        UPDATE work_orders
        SET dispatcher_id = created_by
        WHERE dispatcher_id IS NULL AND technician_id IS NOT NULL AND created_by IS NOT NULL
    """)


def downgrade():
    op.drop_index("ix_work_orders_dispatcher_id", table_name="work_orders")
    op.drop_column("work_orders", "dispatched_at")
    op.drop_column("work_orders", "dispatcher_id")

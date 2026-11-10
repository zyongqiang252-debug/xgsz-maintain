from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import BaseModel


class WorkOrderEditLog(BaseModel):
    """已归档工单的管理员修改记录（审计用）

    changes 结构：{ 字段名: { "before": 旧值, "after": 新值 } }
    """
    __tablename__ = "work_order_edit_logs"

    work_order_id = Column(Integer, ForeignKey("work_orders.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    editor_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    editor_name = Column(String(100))
    status_at_edit = Column(String(16))
    changes = Column(JSONB, comment="字段 -> {before, after}")

    def __repr__(self):
        return f"<WorkOrderEditLog(wo={self.work_order_id} by={self.editor_name})>"

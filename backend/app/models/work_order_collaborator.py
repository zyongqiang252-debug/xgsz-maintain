from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from app.models.base import BaseModel


class WorkOrderCollaborator(BaseModel):
    """工单协作人：一张工单一个主责（work_orders.technician_id），可另挂多个协作人"""
    __tablename__ = "work_order_collaborators"

    work_order_id = Column(Integer, ForeignKey("work_orders.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"),
                     nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("work_order_id", "user_id", name="uq_work_order_collaborator"),
    )

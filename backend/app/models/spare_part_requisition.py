from sqlalchemy import Column, String, Integer, Float, ForeignKey, DateTime, Text

from app.models.base import BaseModel


class SparePartRequisitionStatus:
    """领用申请单状态（不入库为 Enum，避免迁移与历史数据兼容问题）"""
    PENDING = "PENDING"      # 待审批
    APPROVED = "APPROVED"    # 已批准（库存尚未扣减）
    REJECTED = "REJECTED"    # 已驳回
    CANCELLED = "CANCELLED"  # 申请人撤销
    ISSUED = "ISSUED"        # 已出库（库存已扣减，movement_id 有值）

    ALL = (PENDING, APPROVED, REJECTED, CANCELLED, ISSUED)


class SparePartRequisition(BaseModel):
    """备件领用申请单（审批流的数据层）

    流程：维修员提交 PENDING -> 主管 APPROVED / REJECTED
          APPROVED 后由仓管/主管执行出库 ISSUED，并生成 stock_movements(OUT) 流水
    库存只在 ISSUED 时扣减，审批本身不动库存。
    """
    __tablename__ = "spare_part_requisitions"

    part_id = Column(Integer, ForeignKey("spare_parts.id"), nullable=False, index=True)
    part_code = Column(String(50), index=True, comment="冗余存编码，备件改名后仍可追溯")
    part_name = Column(String(200))
    quantity = Column(Float, nullable=False, comment="申请领用数量")
    unit = Column(String(20), default="个")

    work_order_id = Column(Integer, ForeignKey("work_orders.id"), index=True,
                           comment="关联工单（可空：日常备件领用不挂单）")
    reason = Column(Text, comment="领用事由")

    status = Column(String(16), nullable=False, default=SparePartRequisitionStatus.PENDING,
                    index=True, comment="PENDING/APPROVED/REJECTED/CANCELLED/ISSUED")

    applicant_id = Column(Integer, ForeignKey("users.id"), index=True)
    applicant_name = Column(String(100))

    approver_id = Column(Integer, ForeignKey("users.id"))
    approver_name = Column(String(100))
    approved_at = Column(DateTime)
    reject_reason = Column(Text)

    movement_id = Column(Integer, ForeignKey("stock_movements.id"),
                         comment="出库后关联的流水 ID")
    issued_at = Column(DateTime)

    def __repr__(self):
        return (f"<SparePartRequisition({self.part_code} x{self.quantity} "
                f"{self.status})>")

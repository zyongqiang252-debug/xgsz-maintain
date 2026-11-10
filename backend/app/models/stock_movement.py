from sqlalchemy import Column, String, Integer, Float, ForeignKey, TIMESTAMP, Text, JSON, text
from app.models.base import BaseModel


class StockMovement(BaseModel):
    """备件出入库流水

    movement_type:
      - IN      入库（采购/退回）
      - OUT     出库领用（维修消耗，通常带 work_order_id）
      - ADJUST  盘点调整（quantity 为增减量，可为负）
      - RETURN  退回入库
    """
    __tablename__ = "stock_movements"

    part_id = Column(Integer, ForeignKey("spare_parts.id"), nullable=False, index=True)
    part_code = Column(String(50), index=True, comment="冗余存编码，备件被改名也能追溯")
    part_name = Column(String(200))
    movement_type = Column(String(16), nullable=False, index=True)  # IN / OUT / ADJUST / RETURN
    quantity = Column(Float, nullable=False, comment="变动数量（正向为正）")
    before_qty = Column(Float, comment="变动前库存")
    after_qty = Column(Float, comment="变动后库存")
    unit_price = Column(Float, default=0.0)
    amount = Column(Float, default=0.0, comment="金额 = quantity * unit_price")
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), index=True, comment="领用关联的工单")
    operator_id = Column(Integer, ForeignKey("users.id"))
    operator_name = Column(String(100))
    serial_no = Column(String(500), comment="本次出入库的序列号 SN")
    attachments = Column(JSON, comment="照片附件 URL 列表")
    remark = Column(Text)

    def __repr__(self):
        return f"<StockMovement({self.movement_type} {self.part_code} {self.quantity})>"

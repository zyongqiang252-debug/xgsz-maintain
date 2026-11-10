"""盘点单：账面数量 vs 实盘数量，差异要有单据才能改库存

为什么不能直接手工改数：
  1. 财务/审计要看到"谁在什么时候、按哪张单子"把 10 个改成了 8 个；
  2. 盘点差异要能出报表（差异笔数、差异金额、差异率）；
  3. 差异改库存必须留下 ADJUST 流水（红冲），不能静默 UPDATE。
"""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.models.base import BaseModel


class StocktakeStatus:
    DRAFT = "DRAFT"            # 草稿（已生成账面快照）
    COUNTING = "COUNTING"      # 盘点中（部分已录实盘数）
    SUBMITTED = "SUBMITTED"    # 已提交，待审批
    APPROVED = "APPROVED"      # 已审批（差异已改库存并生成 ADJUST 流水）
    CANCELLED = "CANCELLED"    # 已作废

    ALL = (DRAFT, COUNTING, SUBMITTED, APPROVED, CANCELLED)
    LABELS = {
        DRAFT: "草稿", COUNTING: "盘点中", SUBMITTED: "待审批",
        APPROVED: "已审批", CANCELLED: "已作废",
    }


class Stocktake(BaseModel):
    __tablename__ = "stocktakes"

    take_no = Column(String(50), unique=True, nullable=False, index=True)
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), index=True)
    warehouse_name = Column(String(200), comment="仓库名快照")

    status = Column(String(16), nullable=False, default=StocktakeStatus.DRAFT, index=True)

    item_count = Column(Integer, default=0, nullable=False, comment="盘点条目数")
    counted_count = Column(Integer, default=0, nullable=False, comment="已录实盘数条目")
    diff_count = Column(Integer, default=0, nullable=False, comment="有差异条目数")
    diff_amount = Column(Float, default=0.0, nullable=False, comment="差异金额合计（元，正=盘盈）")

    created_by = Column(Integer, ForeignKey("users.id"))
    created_by_name = Column(String(100))
    submitted_at = Column(DateTime)
    approved_by = Column(Integer, ForeignKey("users.id"))
    approved_by_name = Column(String(100))
    approved_at = Column(DateTime)

    remark = Column(Text)

    def __repr__(self):
        return f"<Stocktake({self.take_no} {self.status})>"


class StocktakeItem(BaseModel):
    __tablename__ = "stocktake_items"

    stocktake_id = Column(
        Integer, ForeignKey("stocktakes.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    part_id = Column(Integer, ForeignKey("spare_parts.id"), nullable=False, index=True)
    part_code = Column(String(50), index=True)
    part_name = Column(String(200))
    unit = Column(String(20))
    location_text = Column(String(200), comment="账面库位快照")

    system_qty = Column(Float, nullable=False, default=0.0, comment="账面数量（生成单据时的快照）")
    actual_qty = Column(Float, comment="实盘数量，未盘为空")
    diff_qty = Column(Float, comment="差异 = 实盘 - 账面")
    unit_price = Column(Float, default=0.0)
    diff_amount = Column(Float, default=0.0)
    reason = Column(String(200), comment="差异原因：丢失/损坏/错发/未入账")

    movement_id = Column(Integer, ForeignKey("stock_movements.id"),
                         comment="审批后生成的 ADJUST 流水")

    def __repr__(self):
        return f"<StocktakeItem({self.part_code} {self.system_qty}->{self.actual_qty})>"

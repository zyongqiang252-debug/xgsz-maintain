"""备件实例（一物一码）：SN 级追溯

数量层（spare_parts.stock_quantity）管"有多少"，实例层管"是哪一件"。
两者是并行的两本账：
  - 出入库改了数量，不一定登记实例（散件/耗材类可以不登记）；
  - 登记了实例的件，装到哪台设备、哪张卡位、换下来去哪，全在实例上。
对 GPU 卡、内存、硬盘、光模块这类要追溯 SN 的件，登记实例是硬要求。
"""
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.models.base import BaseModel


class PartInstanceStatus:
    IN_STOCK = "IN_STOCK"      # 在库
    ISSUED = "ISSUED"          # 已出库（领走但还没装到设备上）
    INSTALLED = "INSTALLED"    # 已装机（在某台设备上）
    RMA = "RMA"                # 待返厂（坏件已拆下，等寄回供应商）
    SCRAPPED = "SCRAPPED"      # 已报废

    ALL = (IN_STOCK, ISSUED, INSTALLED, RMA, SCRAPPED)
    LABELS = {
        IN_STOCK: "在库",
        ISSUED: "已出库",
        INSTALLED: "已装机",
        RMA: "待返厂",
        SCRAPPED: "已报废",
    }


class PartInstance(BaseModel):
    __tablename__ = "part_instances"

    part_id = Column(Integer, ForeignKey("spare_parts.id"), nullable=False, index=True)
    part_code = Column(String(50), index=True, comment="冗余存编码，备件改名后仍可追溯")
    part_name = Column(String(200))
    sn = Column(String(100), index=True, comment="序列号；散件可为空")

    status = Column(String(16), nullable=False, default=PartInstanceStatus.IN_STOCK,
                    index=True, comment="IN_STOCK/INSTALLED/RMA/SCRAPPED")

    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), index=True)
    location_id = Column(Integer, ForeignKey("warehouse_locations.id"), index=True)
    location_text = Column(String(200), comment="库位文字快照（库位被删也能看出原来放哪）")

    # 装机去向
    device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    device_code = Column(String(50), index=True)
    gpu_index = Column(Integer, comment="装在第几张卡位（GPU 场景）")
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), index=True)

    unit_price = Column(Float, default=0.0, comment="这件货的入库单价（成本追溯用）")
    supplier = Column(String(200))
    warranty_until = Column(DateTime, comment="保修截止日")

    installed_at = Column(DateTime)
    removed_at = Column(DateTime)
    inbound_movement_id = Column(Integer, ForeignKey("stock_movements.id"))
    outbound_movement_id = Column(Integer, ForeignKey("stock_movements.id"))

    remark = Column(Text)

    def __repr__(self):
        return f"<PartInstance({self.part_code} sn={self.sn} {self.status})>"

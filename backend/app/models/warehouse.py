"""仓库与库位：备件实物的存放地点

一个仓 = 一个物理存放点（主仓 / 现场仓 / 返修仓），库位 = 仓内的货架/柜/层。
备件台账（spare_parts）只记"哪个仓"（warehouse_id），精确到库位的是每件实物
（part_instances.location_id），因为同一编码的备件可能分散在多个柜子里。
"""
from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.models.base import BaseModel


class Warehouse(BaseModel):
    __tablename__ = "warehouses"

    code = Column(String(50), unique=True, nullable=False, index=True, comment="仓库编码，如 MAIN/ON-SITE/REPAIR")
    name = Column(String(200), nullable=False)
    address = Column(String(300), comment="存放地址（机房/楼层/房间）")
    manager_name = Column(String(100), comment="仓管员")
    phone = Column(String(50))
    is_active = Column(Boolean, default=True, nullable=False)
    remark = Column(String(500))

    locations = relationship(
        "WarehouseLocation", back_populates="warehouse",
        cascade="all, delete-orphan", order_by="WarehouseLocation.code",
    )

    def __repr__(self):
        return f"<Warehouse(code='{self.code}', name='{self.name}')>"


class WarehouseLocation(BaseModel):
    __tablename__ = "warehouse_locations"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "code", name="uq_warehouse_location_code"),
    )

    warehouse_id = Column(
        Integer, ForeignKey("warehouses.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    code = Column(String(50), nullable=False, comment="库位编码，如 A-01-3")
    name = Column(String(200))
    rack = Column(String(50), comment="货架号")
    is_active = Column(Boolean, default=True, nullable=False)
    remark = Column(String(500))

    warehouse = relationship("Warehouse", back_populates="locations")

    def __repr__(self):
        return f"<WarehouseLocation(code='{self.code}')>"

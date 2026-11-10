from sqlalchemy import Column, String, Integer, Float, ForeignKey, JSON, Boolean
from app.models.base import BaseModel


class SparePart(BaseModel):
    __tablename__ = "spare_parts"

    part_code = Column(String(50), unique=True, nullable=False, index=True)
    part_name = Column(String(200), nullable=False)
    specification = Column(String(200))
    unit = Column(String(20), default="个")
    stock_quantity = Column(Integer, default=0)
    safety_stock = Column(Integer, default=0)
    unit_price = Column(Float, default=0.0)
    device_type = Column(String(100))
    location = Column(String(200))
    supplier = Column(String(200))
    serial_no = Column(String(500), comment="序列号 SN（当前在库件，可多个逗号分隔）")
    attachments = Column(JSON, comment="照片附件 URL 列表")
    # 是否按 SN 一物一码追溯：勾上后入库必须逐件填 SN（GPU 卡/内存/光模块这类）
    need_sn = Column(Boolean, default=False, nullable=False, server_default="false",
                     comment="是否需要按 SN 追溯")
    # 所属仓库（多仓）；精确库位在 part_instances 上
    warehouse_id = Column(Integer, ForeignKey("warehouses.id"), index=True,
                          comment="所属仓库 ID")
    # 已预占数量：审批通过但还没出库的部分，可用库存 = 现存 - 预占
    reserved_quantity = Column(Integer, default=0, nullable=False, server_default="0",
                               comment="已预占（审批通过未出库）")

    @property
    def available_quantity(self) -> float:
        return float(self.stock_quantity or 0) - float(self.reserved_quantity or 0)

    def __repr__(self):
        return f"<SparePart(part_code='{self.part_code}', part_name='{self.part_name}')>"

from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint
from app.models.base import BaseModel


class CustomerDevice(BaseModel):
    """客户与设备（服务器）绑定：一台设备只归属一个客户"""
    __tablename__ = "customer_devices"

    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"),
                       nullable=False, index=True)

    __table_args__ = (
        UniqueConstraint("device_id", name="uq_customer_device"),
    )

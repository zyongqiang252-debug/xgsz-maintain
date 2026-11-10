from sqlalchemy import Column, String, Integer, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from app.models.base import BaseModel


class CustomerSite(BaseModel):
    """客户机房/站点：报修时选择，工单上保存快照"""
    __tablename__ = "customer_sites"

    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    name = Column(String(100), nullable=False, comment="机房/站点名称")
    address = Column(String(300), comment="详细地址")
    contact_name = Column(String(100))
    contact_phone = Column(String(20))
    is_default = Column(Boolean, default=False, nullable=False)
    remark = Column(String(500))

    customer = relationship("Customer", back_populates="sites")

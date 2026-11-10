from sqlalchemy import Column, String, Integer, Boolean, Text, Date, JSON, ForeignKey
from app.models.base import BaseModel
from sqlalchemy.orm import relationship


class Customer(BaseModel):
    """外部客户（托管服务器的使用方）"""
    __tablename__ = "customers"

    code = Column(String(20), unique=True, index=True, comment="客户编码 KH-0001")
    name = Column(String(100), nullable=False, comment="主联系人姓名")
    phone = Column(String(20), unique=True, nullable=False, index=True, comment="登录手机号")
    company = Column(String(200), comment="客户/公司名称")
    address = Column(String(300), comment="地址/机房")
    level = Column(String(16), default="NORMAL", comment="NORMAL/KEY/VIP")
    tags = Column(JSON, comment="客户标签")
    owner_id = Column(Integer, ForeignKey("users.id"), comment="客户归属人")
    parent_id = Column(Integer, ForeignKey("customers.id"), comment="上级客户/集团")
    contract_no = Column(String(100), comment="合同号")
    service_start = Column(Date, comment="服务开始日期")
    service_end = Column(Date, comment="服务到期日期")
    sla_response_hours = Column(Integer, comment="合同响应时限（小时）")
    sla_resolve_hours = Column(Integer, comment="合同修复时限（小时）")
    password_hash = Column(String(255), comment="客户门户登录密码（bcrypt）")
    remark = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    sites = relationship("CustomerSite", back_populates="customer", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Customer({self.name} {self.phone})>"

from sqlalchemy import Column, String, Integer, Boolean, Text
from app.models.base import BaseModel


class Customer(BaseModel):
    """外部客户（托管服务器的使用方）"""
    __tablename__ = "customers"

    name = Column(String(100), nullable=False, comment="客户联系人姓名")
    phone = Column(String(20), unique=True, nullable=False, index=True, comment="登录手机号")
    company = Column(String(200), comment="客户/公司名称")
    password_hash = Column(String(255), comment="客户门户登录密码（bcrypt）")
    remark = Column(Text)
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    def __repr__(self):
        return f"<Customer({self.name} {self.phone})>"

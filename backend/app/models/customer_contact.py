from sqlalchemy import Column, String, Integer, Boolean, ForeignKey
from app.models.base import BaseModel


class CustomerContact(BaseModel):
    """客户联系人：一个客户可以有多个联系人，主联系人用于门户登录"""
    __tablename__ = "customer_contacts"

    customer_id = Column(Integer, ForeignKey("customers.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    name = Column(String(100), nullable=False)
    phone = Column(String(20), index=True)
    email = Column(String(200))
    title = Column(String(100), comment="职务/角色")
    is_primary = Column(Boolean, default=False, nullable=False)
    remark = Column(String(500))

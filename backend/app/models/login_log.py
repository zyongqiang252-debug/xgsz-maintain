from sqlalchemy import Column, String, Integer, Boolean, Text
from app.models.base import BaseModel


class LoginLog(BaseModel):
    """登录审计：谁、什么时候、从哪个 IP、用的什么方式、成功与否"""
    __tablename__ = "login_logs"

    user_id = Column(Integer, index=True, comment="登录用户（失败时可能为空）")
    username = Column(String(100), index=True)
    real_name = Column(String(100))
    login_type = Column(String(20), default="password", comment="password / code / dingtalk")
    success = Column(Boolean, default=True, index=True)
    reason = Column(String(200), comment="失败原因")
    ip = Column(String(64))
    user_agent = Column(Text)

    def __repr__(self):
        return f"<LoginLog({self.username} {self.success})>"

"""保养计划 / 保养记录 / 点检模板 / 点检记录"""
from datetime import datetime

from sqlalchemy import Column, String, Integer, Float, ForeignKey, TIMESTAMP, Text, Boolean
from sqlalchemy.dialects.postgresql import JSONB

from app.models.base import BaseModel


class MaintenancePlan(BaseModel):
    """保养计划（预防性维护 PM）

    cycle_type: DAYS（按天）/ HOURS（按运行小时，暂按天近似）
    next_due_at：本次到期时间；完成一次保养后按周期顺延
    """
    __tablename__ = "maintenance_plans"

    plan_name = Column(String(200), nullable=False)
    device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    device_code = Column(String(50), index=True)
    items = Column(Text, comment="保养项目（换行分隔）")
    cycle_type = Column(String(16), default="DAYS")
    cycle_value = Column(Integer, default=30, comment="周期数值（天）")
    last_done_at = Column(TIMESTAMP)
    next_due_at = Column(TIMESTAMP, index=True)
    responsible_id = Column(Integer, ForeignKey("users.id"))
    responsible_name = Column(String(100))
    status = Column(String(16), default="ACTIVE", index=True, comment="ACTIVE / PAUSED")
    remark = Column(Text)

    def __repr__(self):
        return f"<MaintenancePlan({self.plan_name} next={self.next_due_at})>"


class MaintenanceRecord(BaseModel):
    """一次保养执行记录"""
    __tablename__ = "maintenance_records"

    plan_id = Column(Integer, ForeignKey("maintenance_plans.id"), index=True)
    device_id = Column(Integer, ForeignKey("devices.id"))
    device_code = Column(String(50))
    plan_name = Column(String(200))
    done_at = Column(TIMESTAMP, default=datetime.now, index=True)
    done_by_id = Column(Integer, ForeignKey("users.id"))
    done_by_name = Column(String(100))
    result = Column(String(16), default="OK", comment="OK / ABNORMAL")
    cost = Column(Float, default=0)
    remark = Column(Text)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), comment="异常时生成的处理工单")


class InspectionTemplate(BaseModel):
    """点检表模板：items = [{name, standard, type: 'check'|'number'}]"""
    __tablename__ = "inspection_templates"

    name = Column(String(200), nullable=False)
    device_type = Column(String(100), index=True)
    items = Column(JSONB, comment="点检项列表")
    active = Column(Boolean, default=True)


class InspectionRecord(BaseModel):
    """点检执行记录：results = [{name, ok, value, remark}]"""
    __tablename__ = "inspection_records"

    template_id = Column(Integer, ForeignKey("inspection_templates.id"), index=True)
    template_name = Column(String(200))
    device_id = Column(Integer, ForeignKey("devices.id"), index=True)
    device_code = Column(String(50), index=True)
    inspector_id = Column(Integer, ForeignKey("users.id"))
    inspector_name = Column(String(100))
    result = Column(String(16), default="OK", index=True, comment="OK / ABNORMAL")
    abnormal_count = Column(Integer, default=0)
    results = Column(JSONB)
    remark = Column(Text)
    work_order_id = Column(Integer, ForeignKey("work_orders.id"), comment="异常转工单")

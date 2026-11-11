from sqlalchemy import (Column, String, Text, Integer, Float, TIMESTAMP, ForeignKey,
                        Boolean, Enum as SQLEnum, DateTime)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from app.models.base import BaseModel
import enum
from datetime import datetime


class WorkOrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    ASSIGNED = "ASSIGNED"
    ACCEPTED = "ACCEPTED"
    ARRIVED = "ARRIVED"
    INSPECTING = "INSPECTING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    ARCHIVING = "ARCHIVING"  # 维修完成，待归档（网页补充表单后归档）
    REJECTED = "REJECTED"
    # 保留旧状态兼容已有数据
    STANDARDIZED = "STANDARDIZED"
    CLASSIFIED = "CLASSIFIED"
    APPROVED = "APPROVED"
    ARCHIVED = "ARCHIVED"


class WorkOrder(BaseModel):
    __tablename__ = "work_orders"

    work_order_no = Column(String(50), unique=True, nullable=False, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"))
    device_code = Column(String(50))  # 扫码获取的设备编码
    fault_object = Column(String(200), comment="涉及对象（集群/网络/其他，非单台设备时填写）")
    fault_code = Column(Text, comment="故障码，多个用逗号分隔")
    device_error_code = Column(String(200), comment="设备运行日志/屏幕报警的错误码（如 SV0436 / 6401），仅带错误码的机电设备填，多个用逗号分隔")
    log_text = Column(Text, comment="设备日志/屏幕原文（错误码录入模式粘贴，供知识抽取抠码与溯源）")
    # ========== GPU 维修专有字段 ==========
    order_type = Column(String(20), index=True, comment="工单类型 REPAIR/MAINTENANCE/INSPECTION/IMPORT")
    alert_level = Column(String(8), index=True, comment="告警级别 P0~P3（优先级推导，SLA 超时升 P0）")
    gpu_index = Column(String(50), comment="故障 GPU 序号，如 GPU3 / 0-7")
    fault_device_sn = Column(String(100), comment="故障部件序列号（GPU 卡/内存条等）")
    service_mode = Column(String(20), index=True, comment="服务方式 REMOTE(远程)/SITE(现场)/RMA(返厂)")
    need_rma = Column(Boolean, comment="是否需要返厂维修")
    # ===== 挂起（等厂商/备件/客户/IDC），SLA 可暂停 =====
    is_on_hold = Column(Boolean, default=False, nullable=False, server_default="false", index=True)
    hold_reason = Column(String(20), comment="VENDOR/SPARE/CUSTOMER/IDC/OTHER")
    hold_remark = Column(Text)
    hold_started_at = Column(DateTime)
    hold_total_minutes = Column(Integer, default=0, server_default="0", nullable=False)
    # ===== RMA / 厂商返修追踪 =====
    rma_vendor = Column(String(200))
    rma_no = Column(String(100))
    rma_status = Column(String(20), comment="PENDING/SHIPPED/RECEIVED/REPAIRED/RETURNED/CLOSED")
    rma_shipped_at = Column(DateTime)
    rma_vendor_received_at = Column(DateTime)
    rma_returned_at = Column(DateTime)
    rma_replacement_sn = Column(String(100))
    rma_remark = Column(Text)
    # ===== 客户验收 =====
    customer_accept_status = Column(String(20), comment="PENDING/ACCEPTED/REJECTED")
    customer_accept_at = Column(DateTime)
    customer_accept_by = Column(String(100))
    customer_accept_remark = Column(Text)
    # ===== 交付单字段 =====
    project_name = Column(String(200))
    delivery_batch = Column(String(100))
    rack_location = Column(String(200))
    power_on_at = Column(DateTime)
    warranty_start = Column(DateTime)
    warranty_end = Column(DateTime)
    fault_description = Column(Text, nullable=False)
    fault_category = Column(String(100), comment="故障大类")
    fault_phenomenon_type = Column(String(200), comment="故障具体现象（级联二级）")
    fault_phenomenon = Column(Text, comment="故障现象补充描述")
    fault_media = Column(JSONB, comment="移动端上报的图片/语音文件URL列表")
    attachments = Column(JSONB, comment="附件列表 [{url, name, type}]")
    root_cause_category = Column(String(100), comment="根本原因大类")
    root_cause_type = Column(String(200), comment="根本原因具体类型（级联二级）")
    root_cause = Column(Text, comment="根本原因补充说明")
    solution_steps = Column(Text)
    solution_ref_knowledge_id = Column(Integer, comment="引用的知识条目ID")
    repair_result = Column(String(20), comment="维修结果: PERMANENT_FIX / TEMPORARY_FIX / UNABLE_FIX")
    follow_up_plan = Column(Text, comment="临时措施后续计划")
    work_hours = Column(Float, comment="工时（小时）")
    used_parts = Column(JSONB)
    start_time = Column(TIMESTAMP)
    end_time = Column(TIMESTAMP)
    technician_id = Column(Integer, ForeignKey("users.id"), comment="指派的维修人员 ID")
    dispatcher_id = Column(Integer, ForeignKey("users.id"), index=True, comment="分配人（派工操作人）")
    dispatched_at = Column(DateTime, comment="最近一次派工时间")
    assignee_id = Column(Integer, ForeignKey("users.id"), comment="当前处理人 ID")
    reporter_id = Column(Integer, ForeignKey("users.id"), comment="上报人员 ID（移动端提交）")
    priority = Column(String(10), default="MEDIUM", comment="优先级: LOW/MEDIUM/HIGH/CRITICAL")
    location = Column(String(200), comment="故障设备位置")
    status = Column(SQLEnum(WorkOrderStatus), default=WorkOrderStatus.DRAFT, nullable=False)
    tags = Column(JSONB)
    confidence = Column(Float, nullable=True, comment="AI 分析置信度 (0-1)")
    analysis_result = Column(JSONB, nullable=True, comment="AI 分析结果完整记录")
    dispatch_score = Column(JSONB, nullable=True, comment="派工评分详情")
    completion_report = Column(JSONB, nullable=True, comment="维修完成报告（工时/备件/照片）")
    created_by = Column(Integer, ForeignKey("users.id"), comment="创建者 ID，仅创建者可编辑")
    customer_id = Column(Integer, ForeignKey("customers.id"), index=True, comment="客户报修来源")
    customer_name = Column(String(100), comment="客户联系人快照")
    customer_company = Column(String(200), comment="客户公司快照")
    customer_phone = Column(String(20), comment="客户手机号快照")
    customer_contact_name = Column(String(100), comment="本次报修联系人")
    customer_contact_phone = Column(String(20), comment="本次报修联系电话")
    customer_site_id = Column(Integer, ForeignKey("customer_sites.id"), comment="客户机房/站点")
    customer_site_name = Column(String(100), comment="机房/站点名称快照")
    customer_address = Column(String(300), comment="客户地址快照")

    # ===== SLA（响应/修复时限，建单时按优先级计算）=====
    response_due_at = Column(TIMESTAMP, comment="响应截止（接单）")
    resolve_due_at = Column(TIMESTAMP, comment="修复截止（完成）")
    first_response_at = Column(TIMESTAMP, comment="首次接单时间")
    resolved_at = Column(TIMESTAMP, comment="完成时间")
    sla_status = Column(String(16), comment="ON_TIME / AT_RISK / OVERDUE")

    # ===== 回访 =====
    satisfaction_score = Column(Integer, comment="满意度 1-5")
    satisfaction_comment = Column(Text, comment="评价内容")
    feedback_at = Column(TIMESTAMP, comment="评价时间")

    # ===== 成本 =====
    labor_cost = Column(Float, comment="人工成本 = 工时 × 单价")
    parts_cost = Column(Float, comment="备件成本")
    total_cost = Column(Float, comment="总成本")

    device = relationship("Device", back_populates="work_orders")
    technician = relationship("User", foreign_keys=[technician_id], lazy="joined")
    progress_logs = relationship(
        "WorkOrderProgressLog", back_populates="work_order",
        order_by="WorkOrderProgressLog.created_at.asc()",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<WorkOrder(work_order_no='{self.work_order_no}', status='{self.status}')>"
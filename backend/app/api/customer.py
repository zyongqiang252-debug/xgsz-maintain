"""客户报修门户 API（免内部账号，手机号 + 验证码登录）

- 客户只能看到绑定给自己的服务器
- 提交报修 → 直接生成 SUBMITTED 工单（来源标记客户），进入待派工池
"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from loguru import logger

from app.core.config import settings
from app.core.database import get_db
from app.core import status_group as SG
from app.models.customer import Customer
from app.models.customer_device import CustomerDevice
from app.models.device import Device
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.models.progress_log import WorkOrderProgressLog
from app.models.user import User, UserRole

router = APIRouter(prefix="/customer", tags=["客户报修门户"])
security_scheme = HTTPBearer(auto_error=False)


class CustomerLoginIn(BaseModel):
    phone: str
    password: str


class CustomerReportIn(BaseModel):
    device_id: Optional[int] = None
    fault_object: Optional[str] = Field(None, max_length=200)
    site_id: Optional[int] = None
    impact_level: Optional[str] = Field(None, description="影响程度 CRITICAL/HIGH/MEDIUM/LOW")
    fault_description: str = Field(..., min_length=2, max_length=500)
    fault_phenomenon: Optional[str] = Field(None, max_length=500)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=20)


class CustomerRatingIn(BaseModel):
    score: int = Field(..., ge=1, le=5)
    comment: Optional[str] = Field(None, max_length=500)


class CustomerAcceptIn(BaseModel):
    accepted: bool = True
    remark: Optional[str] = Field(None, max_length=500)


def create_customer_token(customer: Customer) -> str:
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": str(customer.id), "typ": "customer", "exp": expire},
        settings.SECRET_KEY, algorithm=settings.ALGORITHM,
    )


def get_current_customer(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    db: Session = Depends(get_db),
) -> Customer:
    if credentials is None:
        raise HTTPException(status_code=401, detail="请先登录")
    try:
        payload = jwt.decode(credentials.credentials, settings.SECRET_KEY,
                             algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    if payload.get("typ") != "customer" or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="登录凭证无效")
    customer = db.query(Customer).filter(Customer.id == int(payload["sub"])).first()
    if not customer or not customer.is_active:
        raise HTTPException(status_code=403, detail="客户账号不存在或已停用")
    return customer


def _customer_dict(c: Customer) -> dict:
    return {"id": c.id, "name": c.name, "phone": c.phone,
            "company": c.company or "", "is_active": bool(c.is_active)}


def _device_dict(d: Device) -> dict:
    return {
        "id": d.id, "device_code": d.device_code, "device_name": d.device_name,
        "device_type": d.device_type or "", "model": d.model or "",
        "serial_no": d.serial_no or "", "room": d.room or "", "rack_no": d.rack_no or "",
        "location": d.location or "", "run_status": d.run_status or "",
    }


def _device_location_text(d: Device):
    """位置快照：location 优先，缺机房/机柜时补上，保证工单能定位到机柜"""
    loc = (getattr(d, "location", None) or "").strip()
    room, rack = getattr(d, "room", None), getattr(d, "rack_no", None)
    if loc and room and rack and room in loc and rack in loc:
        return loc
    extra = " / ".join(x for x in [room, rack] if x)
    if extra and extra not in loc:
        return f"{loc}（{extra}）" if loc else extra
    return loc or None


@router.post("/login", summary="客户手机号+密码登录")
def customer_login(data: CustomerLoginIn, db: Session = Depends(get_db)):
    from app.core.password import verify_password
    phone = (data.phone or "").strip()
    if not phone:
        raise HTTPException(status_code=400, detail="请输入手机号")
    customer = db.query(Customer).filter(Customer.phone == phone).first()
    # 失败原因分开提示：客户门户是对外 B 端入口，报错说清楚才能自助解决，
    # 一直回「手机号或密码错误」是此前客户反馈「创建后登不上」的主要来源。
    if not customer:
        logger.info(f"[Customer] 登录失败：手机号未开通客户账号 phone={phone}")
        raise HTTPException(status_code=400, detail="该手机号还没有开通客户账号，请联系服务方管理员")
    if not customer.is_active:
        logger.info(f"[Customer] 登录失败：账号已停用 id={customer.id} phone={phone}")
        raise HTTPException(status_code=403, detail="客户账号已停用，请联系服务方管理员")
    if not customer.password_hash:
        logger.warning(f"[Customer] 登录失败：账号未设置密码 id={customer.id} phone={phone}")
        raise HTTPException(status_code=400, detail="该客户账号还没有设置登录密码，请联系管理员重置密码")
    if not verify_password(data.password, customer.password_hash):
        logger.info(f"[Customer] 登录失败：密码错误 id={customer.id} phone={phone}")
        raise HTTPException(status_code=400, detail="密码错误，请重试；忘记密码请联系服务方管理员重置")
    logger.info(f"[Customer] 登录成功: {customer.name} ({phone})")
    return {"token": create_customer_token(customer), "customer": _customer_dict(customer)}


@router.get("/sites", summary="我的机房/站点")
def my_sites(customer: Customer = Depends(get_current_customer),
             db: Session = Depends(get_db)):
    from app.models.customer_site import CustomerSite
    rows = (db.query(CustomerSite).filter(CustomerSite.customer_id == customer.id)
            .order_by(CustomerSite.is_default.desc(), CustomerSite.id.asc()).all())
    return {"items": [{"id": s.id, "name": s.name, "address": s.address or "",
                       "is_default": bool(s.is_default)} for s in rows]}


@router.get("/devices", summary="我的服务器列表")
def my_devices(customer: Customer = Depends(get_current_customer),
               db: Session = Depends(get_db)):
    rows = (db.query(Device, CustomerDevice)
            .join(CustomerDevice, CustomerDevice.device_id == Device.id)
            .filter(CustomerDevice.customer_id == customer.id)
            .order_by(Device.id.desc()).all())
    return {"items": [_device_dict(d) for d, _ in rows]}


@router.post("/reports", summary="提交报修")
def submit_report(data: CustomerReportIn,
                  customer: Customer = Depends(get_current_customer),
                  db: Session = Depends(get_db)):
    device = None
    if data.device_id:
        device = db.query(Device).filter(Device.id == data.device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")
        bound = db.query(CustomerDevice).filter(
            CustomerDevice.customer_id == customer.id,
            CustomerDevice.device_id == device.id,
        ).first()
        if not bound:
            raise HTTPException(status_code=403, detail="该设备不属于你的账号")

    from app.services.work_order_no import next_work_order_no
    work_order_no = next_work_order_no(db)

    site = None
    if data.site_id:
        from app.models.customer_site import CustomerSite
        site = (db.query(CustomerSite)
                .filter(CustomerSite.id == data.site_id,
                        CustomerSite.customer_id == customer.id).first())
        if not site:
            raise HTTPException(status_code=400, detail="所选机房不属于你的账号")

    from app.services.priority import normalize_priority
    from app.core import alert_level as AL
    pri = normalize_priority(data.impact_level)

    wo = WorkOrder(
        work_order_no=work_order_no,
        device_id=device.id if device else None,
        device_code=device.device_code if device else None,
        fault_device_sn=(device.serial_no if device else None),
        fault_object=(data.fault_object or "").strip() or None,
        fault_description=data.fault_description.strip(),
        fault_phenomenon=(data.fault_phenomenon or "").strip() or None,
        priority=pri,
        alert_level=AL.from_priority(pri),
        location=_device_location_text(device) if device else customer.address,
        status=WorkOrderStatus.SUBMITTED,
        order_type="REPAIR",
        service_mode=None,
        tags=["客户报修"],
        customer_id=customer.id,
        customer_name=customer.name,
        customer_company=customer.company,
        customer_phone=customer.phone,
        customer_contact_name=data.contact_name or customer.name,
        customer_contact_phone=data.contact_phone or customer.phone,
        customer_accept_status="PENDING",
        customer_site_id=site.id if site else None,
        customer_site_name=site.name if site else None,
        customer_address=(site.address if site else None) or customer.address,
    )
    from app.services.fault_classify import classify_fault
    wo.fault_category = classify_fault(wo.fault_description, wo.fault_object)
    # SLA：客户合同时限优先，未配置则按中优先级默认
    from app.services import sla as sla_service
    _now = datetime.now()
    _resp, _resv = sla_service.compute_due(pri, _now)
    if customer.sla_response_hours is not None:
        _resp = _now + timedelta(hours=customer.sla_response_hours)
    if customer.sla_resolve_hours is not None:
        _resv = _now + timedelta(hours=customer.sla_resolve_hours)
    wo.response_due_at = _resp
    wo.resolve_due_at = _resv
    wo.sla_status = "ON_TIME"
    db.add(wo)
    db.flush()
    db.add(WorkOrderProgressLog(
        work_order_id=wo.id,
        from_status=WorkOrderStatus.DRAFT,
        to_status=WorkOrderStatus.SUBMITTED,
        operator_name=customer.name,
        source="CUSTOMER",
        remark=f"客户报修（{customer.phone}）"
               + (f"，联系人：{data.contact_name or customer.name}" if data.contact_name else ""),
    ))
    # 通知主管/管理员：有新客户报修
    try:
        from app.api.notifications import create_notification
        users = db.query(User).filter(
            User.is_active == True,
            User.role.in_([UserRole.ADMIN.value, UserRole.SUPERVISOR.value]),
        ).all()
        for u in users:
            create_notification(
                db, user_id=u.id, type="WORK_ORDER", title="新客户报修待派工",
                content=f"客户 {customer.name}（{customer.company or customer.phone}）报修 "
                        f"{(device.device_name or device.device_code) if device else (wo.fault_object or '集群/网络/其他')}：{data.fault_description[:60]}",
                work_order_id=wo.id, level="P2",
            )
    except Exception as e:
        logger.warning(f"[Customer] 报修通知写入失败（忽略）: {e}")
    db.commit()
    db.refresh(wo)
    logger.info(f"[Customer] 新报修 {work_order_no} 来自 {customer.name} 设备 {(device.device_code if device else (wo.fault_object or '未指定设备'))}")
    return {
        "work_order_id": wo.id,
        "work_order_no": wo.work_order_no,
        "status": wo.status.value if hasattr(wo.status, "value") else str(wo.status),
        "status_label": SG.label_of(wo.status),
        "created_at": wo.created_at.isoformat() if wo.created_at else None,
    }


@router.get("/reports", summary="我的报修记录")
def my_reports(customer: Customer = Depends(get_current_customer),
               db: Session = Depends(get_db)):
    rows = (db.query(WorkOrder)
            .filter(WorkOrder.customer_id == customer.id)
            .order_by(WorkOrder.id.desc()).limit(100).all())
    items = []
    for w in rows:
        items.append({
            "id": w.id,
            "work_order_no": w.work_order_no,
            "device_code": w.device_code,
            "fault_object": w.fault_object,
            "fault_description": w.fault_description,
            "status": w.status.value if hasattr(w.status, "value") else str(w.status),
            "status_label": SG.label_of(w.status),
            "created_at": w.created_at.isoformat() if w.created_at else None,
            "satisfaction_score": w.satisfaction_score,
            "satisfaction_comment": w.satisfaction_comment,
            "can_rate": (w.status == WorkOrderStatus.ARCHIVED and w.satisfaction_score is None),
            "customer_accept_status": w.customer_accept_status,
            "customer_site_name": w.customer_site_name,
            "customer_address": w.customer_address,
            "can_accept": (w.status == WorkOrderStatus.ARCHIVING
                           and w.customer_accept_status != "ACCEPTED"),
        })
    return {"items": items}


@router.post("/reports/{work_order_id}/accept", summary="客户确认解决 / 未解决")
def accept_report(work_order_id: int, data: CustomerAcceptIn,
                  customer: Customer = Depends(get_current_customer),
                  db: Session = Depends(get_db)):
    w = db.query(WorkOrder).filter(
        WorkOrder.id == work_order_id,
        WorkOrder.customer_id == customer.id,
    ).first()
    if not w:
        raise HTTPException(status_code=404, detail="报修工单不存在")
    if w.status != WorkOrderStatus.ARCHIVING:
        raise HTTPException(status_code=400, detail="工单尚未进入待确认阶段")
    now = datetime.now()
    if data.accepted:
        w.customer_accept_status = "ACCEPTED"
        w.customer_accept_at = now
        w.customer_accept_by = customer.name
        w.customer_accept_remark = data.remark
        remark = "客户确认解决"
    else:
        w.customer_accept_status = "REJECTED"
        w.customer_accept_at = now
        w.customer_accept_by = customer.name
        w.customer_accept_remark = data.remark
        w.status = WorkOrderStatus.IN_PROGRESS
        w.resolved_at = None
        remark = f"客户反馈未解决：{data.remark or '未填写原因'}"
    db.add(WorkOrderProgressLog(
        work_order_id=w.id, from_status=WorkOrderStatus.ARCHIVING,
        to_status=w.status, operator_name=customer.name,
        source="CUSTOMER", remark=remark,
    ))
    db.commit()
    return {"message": "已确认解决" if data.accepted else "已反馈未解决，工单退回处理",
            "status": w.status.value if hasattr(w.status, "value") else str(w.status)}


@router.post("/reports/{work_order_id}/rating", summary="客户评价已完成的工单")
def rate_report(work_order_id: int, data: CustomerRatingIn,
                customer: Customer = Depends(get_current_customer),
                db: Session = Depends(get_db)):
    w = db.query(WorkOrder).filter(
        WorkOrder.id == work_order_id,
        WorkOrder.customer_id == customer.id,
    ).first()
    if not w:
        raise HTTPException(status_code=404, detail="报修工单不存在")
    if w.status != WorkOrderStatus.ARCHIVED:
        raise HTTPException(status_code=400, detail="工单完成后才能评价")
    w.satisfaction_score = data.score
    w.satisfaction_comment = data.comment
    w.feedback_at = datetime.now()
    db.commit()
    logger.info(f"[Customer] {customer.name} 评价工单 {w.work_order_no}: {data.score}")
    return {"message": "评价已提交", "score": data.score}

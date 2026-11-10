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
    device_id: int
    fault_description: str = Field(..., min_length=2, max_length=500)
    fault_phenomenon: Optional[str] = Field(None, max_length=500)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=20)


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
        "location": d.location or "", "run_status": d.run_status or "",
    }


@router.post("/login", summary="客户手机号+密码登录")
def customer_login(data: CustomerLoginIn, db: Session = Depends(get_db)):
    from app.core.password import verify_password
    phone = (data.phone or "").strip()
    customer = db.query(Customer).filter(Customer.phone == phone).first()
    if not customer or not customer.is_active:
        raise HTTPException(status_code=400, detail="手机号或密码错误")
    if not customer.password_hash or not verify_password(data.password, customer.password_hash):
        raise HTTPException(status_code=400, detail="手机号或密码错误")
    logger.info(f"[Customer] 登录成功: {customer.name} ({phone})")
    return {"token": create_customer_token(customer), "customer": _customer_dict(customer)}


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
    device = db.query(Device).filter(Device.id == data.device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    bound = db.query(CustomerDevice).filter(
        CustomerDevice.customer_id == customer.id,
        CustomerDevice.device_id == device.id,
    ).first()
    if not bound:
        raise HTTPException(status_code=403, detail="该设备不属于你的账号")

    today = datetime.now().strftime("%Y%m%d")
    prefix = f"WO-{today}-"
    latest = (db.query(WorkOrder)
              .filter(WorkOrder.work_order_no.like(f"{prefix}%"))
              .order_by(WorkOrder.work_order_no.desc()).first())
    seq = 1
    if latest and latest.work_order_no.startswith(prefix):
        try:
            seq = int(latest.work_order_no.split("-")[-1]) + 1
        except ValueError:
            seq = 1
    work_order_no = f"{prefix}{seq:03d}"

    wo = WorkOrder(
        work_order_no=work_order_no,
        device_id=device.id,
        device_code=device.device_code,
        fault_description=data.fault_description.strip(),
        fault_phenomenon=(data.fault_phenomenon or "").strip() or None,
        priority="MEDIUM",
        location=device.location,
        status=WorkOrderStatus.SUBMITTED,
        order_type="REPAIR",
        tags=["客户报修"],
        customer_id=customer.id,
        customer_name=customer.name,
        customer_company=customer.company,
        customer_phone=customer.phone,
        customer_contact_name=data.contact_name or customer.name,
        customer_contact_phone=data.contact_phone or customer.phone,
    )
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
                        f"{device.device_name or device.device_code}：{data.fault_description[:60]}",
                work_order_id=wo.id, level="P2",
            )
    except Exception as e:
        logger.warning(f"[Customer] 报修通知写入失败（忽略）: {e}")
    db.commit()
    db.refresh(wo)
    logger.info(f"[Customer] 新报修 {work_order_no} 来自 {customer.name} 设备 {device.device_code}")
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
            "fault_description": w.fault_description,
            "status": w.status.value if hasattr(w.status, "value") else str(w.status),
            "status_label": SG.label_of(w.status),
            "created_at": w.created_at.isoformat() if w.created_at else None,
        })
    return {"items": items}

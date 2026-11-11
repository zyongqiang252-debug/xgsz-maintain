"""客户管理（内部管理员/主管）：客户 360、联系人、设备绑定、工单历史、报表"""
import io
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_supervisor
from app.models.customer import Customer
from app.models.customer_contact import CustomerContact
from app.models.customer_site import CustomerSite
from app.models.customer_device import CustomerDevice
from app.models.device import Device
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderStatus

router = APIRouter(prefix="/customers", tags=["客户管理"],
                   dependencies=[Depends(get_current_user)])


class CustomerIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=6, max_length=20)
    password: Optional[str] = Field(None, min_length=6, max_length=72)
    company: Optional[str] = Field(None, max_length=200)
    address: Optional[str] = Field(None, max_length=300)
    level: Optional[str] = "NORMAL"
    tags: Optional[List[str]] = None
    owner_id: Optional[int] = None
    parent_id: Optional[int] = None
    contract_no: Optional[str] = None
    service_start: Optional[date] = None
    service_end: Optional[date] = None
    sla_response_hours: Optional[int] = Field(None, ge=0, le=720)
    sla_resolve_hours: Optional[int] = Field(None, ge=0, le=720)
    remark: Optional[str] = None
    is_active: bool = True


class ContactIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: Optional[str] = Field(None, max_length=20)
    email: Optional[str] = Field(None, max_length=200)
    title: Optional[str] = Field(None, max_length=100)
    is_primary: bool = False
    remark: Optional[str] = Field(None, max_length=500)


class CustomerDevicesIn(BaseModel):
    device_ids: List[int] = []


LEVEL_LABELS = {"NORMAL": "普通", "KEY": "重点", "VIP": "VIP"}
OPEN_STATUSES = [
    WorkOrderStatus.DRAFT, WorkOrderStatus.SUBMITTED, WorkOrderStatus.ASSIGNED,
    WorkOrderStatus.ACCEPTED, WorkOrderStatus.ARRIVED, WorkOrderStatus.INSPECTING,
    WorkOrderStatus.IN_PROGRESS, WorkOrderStatus.ARCHIVING,
]


def _sla_label(w: WorkOrder) -> str:
    if w.sla_status == "OVERDUE":
        return "已超时"
    return "正常"


def _cust_dict(db: Session, c: Customer, detail: bool = False) -> dict:
    devices = (db.query(Device, CustomerDevice)
               .join(CustomerDevice, CustomerDevice.device_id == Device.id)
               .filter(CustomerDevice.customer_id == c.id).all())
    total = db.query(func.count(WorkOrder.id)).filter(WorkOrder.customer_id == c.id).scalar() or 0
    open_cnt = (db.query(func.count(WorkOrder.id))
                .filter(WorkOrder.customer_id == c.id, WorkOrder.status.in_(OPEN_STATUSES)).scalar() or 0)
    archived = (db.query(func.count(WorkOrder.id))
                .filter(WorkOrder.customer_id == c.id,
                        WorkOrder.status == WorkOrderStatus.ARCHIVED).scalar() or 0)
    overdue = (db.query(func.count(WorkOrder.id))
               .filter(WorkOrder.customer_id == c.id,
                       WorkOrder.sla_status == "OVERDUE").scalar() or 0)
    last = (db.query(func.max(WorkOrder.created_at))
            .filter(WorkOrder.customer_id == c.id).scalar())
    avg_score = (db.query(func.avg(WorkOrder.satisfaction_score))
                 .filter(WorkOrder.customer_id == c.id,
                         WorkOrder.satisfaction_score.isnot(None)).scalar())
    owner = db.query(User).filter(User.id == c.owner_id).first() if c.owner_id else None
    parent = db.query(Customer).filter(Customer.id == c.parent_id).first() if c.parent_id else None
    d = {
        "id": c.id, "code": c.code or f"KH-{c.id:04d}", "name": c.name, "phone": c.phone,
        "company": c.company or "", "address": c.address or "",
        "level": c.level or "NORMAL", "level_label": LEVEL_LABELS.get(c.level, "普通"),
        "tags": c.tags or [], "owner_id": c.owner_id,
        "owner_name": owner.real_name if owner else "",
        "parent_id": c.parent_id, "parent_name": parent.company or parent.name if parent else "",
        "contract_no": c.contract_no or "",
        "service_start": c.service_start.isoformat() if c.service_start else None,
        "service_end": c.service_end.isoformat() if c.service_end else None,
        "sla_response_hours": c.sla_response_hours,
        "sla_resolve_hours": c.sla_resolve_hours,
        "remark": c.remark or "", "is_active": bool(c.is_active),
        "has_password": bool(c.password_hash),
        "devices": [{"id": dv.id, "device_code": dv.device_code,
                     "device_name": dv.device_name, "location": dv.location or ""}
                    for dv, _ in devices],
        "device_count": len(devices),
        "order_count": int(total), "open_count": int(open_cnt),
        "archived_count": int(archived), "overdue_count": int(overdue),
        "last_order_at": last.isoformat() if last else None,
        "avg_satisfaction": round(float(avg_score), 2) if avg_score is not None else None,
    }
    if detail:
        contact_rows = (db.query(CustomerContact)
                        .filter(CustomerContact.customer_id == c.id)
                        .order_by(CustomerContact.is_primary.desc(), CustomerContact.id.asc()).all())
        d["contacts"] = [{"id": x.id, "name": x.name, "phone": x.phone or "",
                          "email": x.email or "", "title": x.title or "",
                          "is_primary": bool(x.is_primary), "remark": x.remark or ""}
                         for x in contact_rows]
        recent = (db.query(WorkOrder).filter(WorkOrder.customer_id == c.id)
                  .order_by(WorkOrder.id.desc()).limit(10).all())
        d["recent_orders"] = [_order_brief(w) for w in recent]
        site_rows = (db.query(CustomerSite)
                     .filter(CustomerSite.customer_id == c.id)
                     .order_by(CustomerSite.is_default.desc(), CustomerSite.id.asc()).all())
        d["sites"] = [{"id": x.id, "name": x.name, "address": x.address or "",
                       "contact_name": x.contact_name or "", "contact_phone": x.contact_phone or "",
                       "is_default": bool(x.is_default), "remark": x.remark or ""}
                      for x in site_rows]
    return d

class SiteIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    address: Optional[str] = Field(None, max_length=300)
    contact_name: Optional[str] = Field(None, max_length=100)
    contact_phone: Optional[str] = Field(None, max_length=20)
    is_default: bool = False
    remark: Optional[str] = Field(None, max_length=500)

@router.get("/{customer_id}/sites", summary="客户机房/站点")
def list_sites(customer_id: int, db: Session = Depends(get_db)):
    rows = (db.query(CustomerSite).filter(CustomerSite.customer_id == customer_id)
            .order_by(CustomerSite.is_default.desc(), CustomerSite.id.asc()).all())
    return {"items": [{"id": x.id, "name": x.name, "address": x.address or "",
                       "contact_name": x.contact_name or "", "contact_phone": x.contact_phone or "",
                       "is_default": bool(x.is_default), "remark": x.remark or ""} for x in rows]}

@router.post("/{customer_id}/sites", summary="新增客户机房", dependencies=[Depends(require_supervisor)])
def add_site(customer_id: int, data: SiteIn, db: Session = Depends(get_db)):
    if not db.query(Customer).filter(Customer.id == customer_id).first():
        raise HTTPException(status_code=404, detail="客户不存在")
    if data.is_default:
        db.query(CustomerSite).filter(CustomerSite.customer_id == customer_id).update(
            {CustomerSite.is_default: False})
    s = CustomerSite(customer_id=customer_id, name=data.name, address=data.address,
                     contact_name=data.contact_name, contact_phone=data.contact_phone,
                     is_default=data.is_default, remark=data.remark)
    db.add(s); db.commit(); db.refresh(s)
    return {"id": s.id, "name": s.name}

@router.put("/{customer_id}/sites/{site_id}", summary="修改客户机房", dependencies=[Depends(require_supervisor)])
def update_site(customer_id: int, site_id: int, data: SiteIn, db: Session = Depends(get_db)):
    s = (db.query(CustomerSite).filter(CustomerSite.id == site_id,
                                       CustomerSite.customer_id == customer_id).first())
    if not s:
        raise HTTPException(status_code=404, detail="机房不存在")
    if data.is_default:
        db.query(CustomerSite).filter(CustomerSite.customer_id == customer_id).update(
            {CustomerSite.is_default: False})
    s.name = data.name
    s.address = data.address
    s.contact_name = data.contact_name
    s.contact_phone = data.contact_phone
    s.is_default = data.is_default
    s.remark = data.remark
    db.commit()
    return {"message": "已保存"}

@router.delete("/{customer_id}/sites/{site_id}", summary="删除客户机房", dependencies=[Depends(require_supervisor)])
def delete_site(customer_id: int, site_id: int, db: Session = Depends(get_db)):
    s = (db.query(CustomerSite).filter(CustomerSite.id == site_id,
                                       CustomerSite.customer_id == customer_id).first())
    if not s:
        raise HTTPException(status_code=404, detail="机房不存在")
    db.delete(s); db.commit()
    return {"message": "已删除"}


def _order_brief(w: WorkOrder) -> dict:
    return {
        "id": w.id, "work_order_no": w.work_order_no,
        "device_code": w.device_code or "", "fault_description": w.fault_description,
        "status": w.status.value if hasattr(w.status, "value") else str(w.status),
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "technician_id": w.technician_id,
        "assignee_id": getattr(w, "assignee_id", None),
        "technician_name": w.technician.real_name if getattr(w, "technician", None) else "",
        "sla_status": w.sla_status or "",
        "satisfaction_score": w.satisfaction_score,
    }


@router.get("/", summary="客户列表")
def list_customers(
    keyword: Optional[str] = None,
    level: Optional[str] = None,
    tag: Optional[str] = None,
    active: Optional[bool] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Customer)
    if keyword:
        like = f"%{keyword.strip()}%"
        q = q.filter(Customer.code.ilike(like) | Customer.name.ilike(like) |
                     Customer.company.ilike(like) | Customer.phone.ilike(like))
    if level:
        q = q.filter(Customer.level == level.upper())
    if active is not None:
        q = q.filter(Customer.is_active == active)
    rows = q.order_by(Customer.id.desc()).all()
    items = [_cust_dict(db, c) for c in rows]
    if tag:
        items = [x for x in items if tag in (x.get("tags") or [])]
    return {"total": len(items), "items": items}


@router.post("/", summary="新建客户", dependencies=[Depends(require_supervisor)])
def create_customer(data: CustomerIn, db: Session = Depends(get_db)):
    if db.query(Customer).filter(Customer.phone == data.phone.strip()).first():
        raise HTTPException(status_code=400, detail="该手机号已存在客户账号")
    # 自动客户编码 KH-0001
    seq = (db.query(func.count(Customer.id)).scalar() or 0) + 1
    while True:
        code = f"KH-{seq:04d}"
        if not db.query(Customer).filter(Customer.code == code).first():
            break
        seq += 1
    from app.core.password import hash_password
    c = Customer(
        code=code, name=data.name.strip(), phone=data.phone.strip(),
        company=(data.company or "").strip() or None, address=data.address,
        level=(data.level or "NORMAL").upper(), tags=data.tags or [],
        owner_id=data.owner_id, parent_id=data.parent_id,
        contract_no=data.contract_no, service_start=data.service_start,
        service_end=data.service_end, sla_response_hours=data.sla_response_hours,
        sla_resolve_hours=data.sla_resolve_hours, remark=data.remark,
        is_active=data.is_active,
    )
    c.password_hash = hash_password(data.password or "123456")
    db.add(c)
    db.flush()
    # 主联系人同时写入联系人表
    db.add(CustomerContact(customer_id=c.id, name=c.name, phone=c.phone,
                           title="主联系人", is_primary=True))
    db.commit()
    db.refresh(c)
    return _cust_dict(db, c, detail=True)


@router.get("/{customer_id}", summary="客户详情（360）")
def get_customer(customer_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    # 联系人/机房/最近工单等明细仅管理员/主管可见；技术员只读基本信息
    role = getattr(current_user.role, "value", current_user.role) or ""
    detail = role.upper() in ("ADMIN", "SUPERVISOR")
    return _cust_dict(db, c, detail=detail)


@router.put("/{customer_id}", summary="修改客户", dependencies=[Depends(require_supervisor)])
def update_customer(customer_id: int, data: CustomerIn, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    dup = db.query(Customer).filter(Customer.phone == data.phone.strip(),
                                    Customer.id != customer_id).first()
    if dup:
        raise HTTPException(status_code=400, detail="该手机号已被其他客户使用")
    c.name = data.name.strip()
    c.phone = data.phone.strip()
    c.company = (data.company or "").strip() or None
    c.address = data.address
    c.level = (data.level or "NORMAL").upper()
    c.tags = data.tags or []
    c.owner_id = data.owner_id
    c.parent_id = data.parent_id
    c.contract_no = data.contract_no
    c.service_start = data.service_start
    c.service_end = data.service_end
    c.sla_response_hours = data.sla_response_hours
    c.sla_resolve_hours = data.sla_resolve_hours
    c.remark = data.remark
    c.is_active = data.is_active
    if data.password:
        from app.core.password import hash_password
        c.password_hash = hash_password(data.password)
    db.commit()
    db.refresh(c)
    return _cust_dict(db, c, detail=True)


@router.delete("/{customer_id}", summary="停用客户（不物理删除）", dependencies=[Depends(require_supervisor)])
def deactivate_customer(customer_id: int, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    c.is_active = False
    db.commit()
    return {"message": "客户已停用，历史工单与设备绑定保留"}


@router.get("/{customer_id}/devices", summary="客户绑定设备")
def customer_devices(customer_id: int, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    rows = (db.query(Device, CustomerDevice)
            .join(CustomerDevice, CustomerDevice.device_id == Device.id)
            .filter(CustomerDevice.customer_id == customer_id).all())
    return {"items": [{"id": d.id, "device_code": d.device_code,
                       "device_name": d.device_name, "location": d.location or ""}
                      for d, _ in rows]}


@router.put("/{customer_id}/devices", summary="覆盖式绑定客户设备", dependencies=[Depends(require_supervisor)])
def bind_devices(customer_id: int, data: CustomerDevicesIn, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    ids = list(dict.fromkeys([int(i) for i in data.device_ids]))
    conflict = (db.query(CustomerDevice)
                .filter(CustomerDevice.device_id.in_(ids),
                        CustomerDevice.customer_id != customer_id).first()) if ids else None
    if conflict:
        d = db.query(Device).filter(Device.id == conflict.device_id).first()
        raise HTTPException(status_code=400,
                            detail=f"设备 {d.device_code if d else conflict.device_id} 已绑定其他客户")
    db.query(CustomerDevice).filter(CustomerDevice.customer_id == customer_id).delete()
    for did in ids:
        if db.query(Device).filter(Device.id == did).first():
            db.add(CustomerDevice(customer_id=customer_id, device_id=did))
    db.commit()
    return _cust_dict(db, c, detail=True)


@router.get("/{customer_id}/orders", summary="客户工单历史")
def customer_orders(customer_id: int,
                    page: int = Query(1, ge=1),
                    page_size: int = Query(20, ge=1, le=100),
                    db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    q = db.query(WorkOrder).filter(WorkOrder.customer_id == customer_id)
    total = q.count()
    rows = (q.order_by(WorkOrder.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_order_brief(w) for w in rows]}


@router.get("/{customer_id}/orders/{work_order_id}", summary="客户工单详情（只读，客户服务历史）")
def customer_order_detail(customer_id: int, work_order_id: int,
                          db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """客户页里查看某张工单的只读详情：含处理过程，不含成本/内部账号信息。

    权限：任何登录用户都可以看，但必须属于该客户；这是客户服务历史的只读视图，
    操作仍需回到工单模块（且受工单归属权限控制）。
    """
    from app.core import status_group as SG
    from app.models.progress_log import WorkOrderProgressLog

    w = (db.query(WorkOrder)
         .filter(WorkOrder.id == work_order_id, WorkOrder.customer_id == customer_id)
         .first())
    if not w:
        raise HTTPException(status_code=404, detail="该客户下没有这张工单")
    tech = db.query(User).filter(User.id == w.technician_id).first() if w.technician_id else None
    logs = (db.query(WorkOrderProgressLog)
            .filter(WorkOrderProgressLog.work_order_id == w.id)
            .order_by(WorkOrderProgressLog.created_at.asc(), WorkOrderProgressLog.id.asc())
            .limit(100).all())
    return {
        "id": w.id,
        "work_order_no": w.work_order_no,
        "status": w.status.value if hasattr(w.status, "value") else str(w.status),
        "status_label": SG.label_of(w.status),
        "device_code": w.device_code or "",
        "fault_description": w.fault_description,
        "fault_phenomenon": w.fault_phenomenon,
        "root_cause": w.root_cause,
        "solution_steps": w.solution_steps,
        "repair_result": w.repair_result,
        "work_hours": w.work_hours,
        "technician_id": w.technician_id,
        "technician_name": tech.real_name if tech else "",
        "customer_accept_status": w.customer_accept_status,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "resolved_at": w.resolved_at.isoformat() if w.resolved_at else None,
        "progress": [{
            "id": x.id,
            "from_status": x.from_status.value if hasattr(x.from_status, "value") else x.from_status,
            "to_status": x.to_status.value if hasattr(x.to_status, "value") else x.to_status,
            "operator_name": x.operator_name,
            "source": x.source,
            "remark": x.remark,
            "created_at": x.created_at.isoformat() if x.created_at else None,
        } for x in logs],
    }


# ==================== 联系人 ====================

@router.get("/{customer_id}/contacts", summary="客户联系人", dependencies=[Depends(require_supervisor)])
def list_contacts(customer_id: int, db: Session = Depends(get_db)):
    rows = (db.query(CustomerContact)
            .filter(CustomerContact.customer_id == customer_id)
            .order_by(CustomerContact.is_primary.desc(), CustomerContact.id.asc()).all())
    return {"items": [{"id": x.id, "name": x.name, "phone": x.phone or "",
                       "email": x.email or "", "title": x.title or "",
                       "is_primary": bool(x.is_primary), "remark": x.remark or ""}
                      for x in rows]}


@router.post("/{customer_id}/contacts", summary="新增联系人", dependencies=[Depends(require_supervisor)])
def add_contact(customer_id: int, data: ContactIn, db: Session = Depends(get_db)):
    if not db.query(Customer).filter(Customer.id == customer_id).first():
        raise HTTPException(status_code=404, detail="客户不存在")
    if data.is_primary:
        db.query(CustomerContact).filter(CustomerContact.customer_id == customer_id).update(
            {CustomerContact.is_primary: False})
    c = CustomerContact(customer_id=customer_id, name=data.name, phone=data.phone,
                        email=data.email, title=data.title, is_primary=data.is_primary,
                        remark=data.remark)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": c.id, "name": c.name, "phone": c.phone or "", "email": c.email or "",
            "title": c.title or "", "is_primary": bool(c.is_primary), "remark": c.remark or ""}


@router.put("/{customer_id}/contacts/{contact_id}", summary="修改联系人", dependencies=[Depends(require_supervisor)])
def update_contact(customer_id: int, contact_id: int, data: ContactIn,
                   db: Session = Depends(get_db)):
    c = (db.query(CustomerContact)
         .filter(CustomerContact.id == contact_id,
                 CustomerContact.customer_id == customer_id).first())
    if not c:
        raise HTTPException(status_code=404, detail="联系人不存在")
    if data.is_primary:
        db.query(CustomerContact).filter(CustomerContact.customer_id == customer_id).update(
            {CustomerContact.is_primary: False})
    c.name = data.name
    c.phone = data.phone
    c.email = data.email
    c.title = data.title
    c.is_primary = data.is_primary
    c.remark = data.remark
    db.commit()
    return {"message": "已保存"}


@router.delete("/{customer_id}/contacts/{contact_id}", summary="删除联系人", dependencies=[Depends(require_supervisor)])
def delete_contact(customer_id: int, contact_id: int, db: Session = Depends(get_db)):
    c = (db.query(CustomerContact)
         .filter(CustomerContact.id == contact_id,
                 CustomerContact.customer_id == customer_id).first())
    if not c:
        raise HTTPException(status_code=404, detail="联系人不存在")
    if c.is_primary:
        raise HTTPException(status_code=400, detail="主联系人不能删除")
    db.delete(c)
    db.commit()
    return {"message": "已删除"}


@router.get("/{customer_id}/export", summary="导出客户服务报告", dependencies=[Depends(require_supervisor)])
def export_customer(customer_id: int, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "客户信息"
    info = _cust_dict(db, c, detail=True)
    rows = [
        ("客户编码", info["code"]), ("客户名称", info["company"]), ("联系人", info["name"]),
        ("手机号", info["phone"]), ("地址", info["address"]), ("级别", info["level_label"]),
        ("合同号", info["contract_no"]), ("服务开始", info["service_start"]),
        ("服务到期", info["service_end"]), ("工单总数", info["order_count"]),
        ("未完成", info["open_count"]), ("已归档", info["archived_count"]),
        ("超时", info["overdue_count"]), ("平均满意度", info["avg_satisfaction"]),
    ]
    for r in rows:
        ws.append(list(r))
    ws2 = wb.create_sheet("工单明细")
    ws2.append(["工单号", "设备", "故障描述", "状态", "负责人", "提交时间", "满意度"])
    orders = (db.query(WorkOrder).filter(WorkOrder.customer_id == customer_id)
              .order_by(WorkOrder.id.desc()).all())
    status_labels = {"DRAFT": "草稿", "SUBMITTED": "待派工", "ASSIGNED": "已派单",
                     "ACCEPTED": "已接单", "ARRIVED": "已到场", "INSPECTING": "检查中",
                     "IN_PROGRESS": "维修中", "ARCHIVING": "待归档", "ARCHIVED": "已归档",
                     "REJECTED": "已退回"}
    for w in orders:
        ws2.append([w.work_order_no, w.device_code, w.fault_description,
                    status_labels.get(w.status.value if hasattr(w.status, "value") else w.status, ""),
                    w.technician.real_name if getattr(w, "technician", None) else "",
                    w.created_at.strftime("%Y-%m-%d %H:%M") if w.created_at else "",
                    w.satisfaction_score])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=customer-{c.code or c.id}.xlsx"},
    )

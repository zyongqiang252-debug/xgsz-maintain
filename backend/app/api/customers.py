"""客户管理（内部管理员/主管）：客户账号 + 设备绑定"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_supervisor
from app.models.customer import Customer
from app.models.customer_device import CustomerDevice
from app.models.device import Device

router = APIRouter(prefix="/customers", tags=["客户管理"],
                   dependencies=[Depends(require_supervisor)])


class CustomerIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=6, max_length=20)
    password: Optional[str] = Field(None, min_length=6, max_length=72, description="客户门户登录密码；新建不填默认 123456")
    company: Optional[str] = Field(None, max_length=200)
    remark: Optional[str] = None
    is_active: bool = True


class CustomerDevicesIn(BaseModel):
    device_ids: List[int] = []


def _cust_dict(db: Session, c: Customer) -> dict:
    devices = (db.query(Device, CustomerDevice)
               .join(CustomerDevice, CustomerDevice.device_id == Device.id)
               .filter(CustomerDevice.customer_id == c.id).all())
    return {
        "id": c.id, "name": c.name, "phone": c.phone,
        "company": c.company or "", "remark": c.remark or "",
        "is_active": bool(c.is_active),
        "has_password": bool(c.password_hash),
        "devices": [{"id": d.id, "device_code": d.device_code,
                     "device_name": d.device_name, "location": d.location or ""}
                    for d, _ in devices],
        "device_count": len(devices),
    }


@router.get("/", summary="客户列表")
def list_customers(db: Session = Depends(get_db)):
    rows = db.query(Customer).order_by(Customer.id.desc()).all()
    return {"total": len(rows), "items": [_cust_dict(db, c) for c in rows]}


@router.post("/", summary="新建客户")
def create_customer(data: CustomerIn, db: Session = Depends(get_db)):
    if db.query(Customer).filter(Customer.phone == data.phone.strip()).first():
        raise HTTPException(status_code=400, detail="该手机号已存在客户账号")
    c = Customer(name=data.name.strip(), phone=data.phone.strip(),
                 company=(data.company or "").strip() or None,
                 remark=data.remark, is_active=data.is_active)
    from app.core.password import hash_password
    c.password_hash = hash_password(data.password or "123456")
    db.add(c)
    db.commit()
    db.refresh(c)
    return _cust_dict(db, c)


@router.put("/{customer_id}", summary="修改客户")
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
    c.remark = data.remark
    c.is_active = data.is_active
    if data.password:
        from app.core.password import hash_password
        c.password_hash = hash_password(data.password)
    db.commit()
    db.refresh(c)
    return _cust_dict(db, c)


@router.delete("/{customer_id}", summary="删除客户")
def delete_customer(customer_id: int, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    db.query(CustomerDevice).filter(CustomerDevice.customer_id == customer_id).delete()
    db.delete(c)
    db.commit()
    return {"message": "客户已删除"}


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


@router.put("/{customer_id}/devices", summary="覆盖式绑定客户设备")
def bind_devices(customer_id: int, data: CustomerDevicesIn, db: Session = Depends(get_db)):
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        raise HTTPException(status_code=404, detail="客户不存在")
    ids = list(dict.fromkeys([int(i) for i in data.device_ids]))
    # 设备只能属于一个客户
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
    return _cust_dict(db, c)

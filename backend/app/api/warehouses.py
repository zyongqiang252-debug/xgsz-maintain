"""仓库与库位 API

- 仓库：主仓 / 现场仓 / 返修仓，备件台账上的 warehouse_id 指这边
- 库位：仓内的货架/柜/层，精确到库位的是实物实例（part_instances.location_id）

权限：查询=登录即可；增删改=管理员/主管。
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_supervisor
from app.models.part_instance import PartInstance
from app.models.spare_part import SparePart
from app.models.user import User
from app.models.warehouse import Warehouse, WarehouseLocation

router = APIRouter(tags=["仓库库位"], dependencies=[Depends(get_current_user)])


class WarehouseIn(BaseModel):
    code: str = Field(..., max_length=50)
    name: str = Field(..., max_length=200)
    address: Optional[str] = None
    manager_name: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool = True
    remark: Optional[str] = None


class LocationIn(BaseModel):
    code: str = Field(..., max_length=50)
    name: Optional[str] = None
    rack: Optional[str] = None
    is_active: bool = True
    remark: Optional[str] = None


def _wh_dict(w: Warehouse, location_count: Optional[int] = None,
             part_count: Optional[int] = None) -> dict:
    d = {
        "id": w.id, "code": w.code, "name": w.name, "address": w.address,
        "manager_name": w.manager_name, "phone": w.phone,
        "is_active": bool(w.is_active), "remark": w.remark,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }
    if location_count is not None:
        d["location_count"] = location_count
    if part_count is not None:
        d["part_count"] = part_count
    return d


def _loc_dict(loc: WarehouseLocation) -> dict:
    return {
        "id": loc.id, "warehouse_id": loc.warehouse_id, "code": loc.code,
        "name": loc.name, "rack": loc.rack, "is_active": bool(loc.is_active),
        "remark": loc.remark,
    }


@router.get("/", summary="仓库列表")
def list_warehouses(
    include_inactive: bool = Query(False),
    db: Session = Depends(get_db),
):
    q = db.query(Warehouse)
    if not include_inactive:
        q = q.filter(Warehouse.is_active.is_(True))
    rows = q.order_by(Warehouse.id).all()

    loc_counts = dict(
        db.query(WarehouseLocation.warehouse_id, func.count(WarehouseLocation.id))
        .group_by(WarehouseLocation.warehouse_id).all()
    )
    part_counts = dict(
        db.query(SparePart.warehouse_id, func.count(SparePart.id))
        .filter(SparePart.warehouse_id.isnot(None))
        .group_by(SparePart.warehouse_id).all()
    )
    return {"items": [
        _wh_dict(w, loc_counts.get(w.id, 0), part_counts.get(w.id, 0)) for w in rows
    ]}


@router.post("/", summary="新建仓库（主管/管理员）")
def create_warehouse(data: WarehouseIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_supervisor)):
    if db.query(Warehouse).filter(Warehouse.code == data.code).first():
        raise HTTPException(status_code=400, detail="仓库编码已存在")
    w = Warehouse(**data.model_dump())
    db.add(w)
    db.commit()
    db.refresh(w)
    logger.info(f"[Warehouse] 新建仓库 {w.code}")
    return _wh_dict(w, 0, 0)


@router.put("/{warehouse_id}", summary="修改仓库（主管/管理员）")
def update_warehouse(warehouse_id: int, data: WarehouseIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_supervisor)):
    w = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="仓库不存在")
    if data.code != w.code and db.query(Warehouse).filter(Warehouse.code == data.code).first():
        raise HTTPException(status_code=400, detail="仓库编码已存在")
    for k, v in data.model_dump().items():
        setattr(w, k, v)
    db.commit()
    db.refresh(w)
    return _wh_dict(w)


@router.delete("/{warehouse_id}", summary="删除仓库（主管/管理员）")
def delete_warehouse(warehouse_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(require_supervisor)):
    w = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="仓库不存在")
    used = db.query(SparePart).filter(SparePart.warehouse_id == warehouse_id).count()
    if used:
        raise HTTPException(status_code=400,
                            detail=f"该仓还有 {used} 条备件台账，先把备件改到别的仓或停用仓库")
    inst = db.query(PartInstance).filter(PartInstance.warehouse_id == warehouse_id).count()
    if inst:
        raise HTTPException(status_code=400,
                            detail=f"该仓还有 {inst} 件实物实例，不能删除")
    db.delete(w)
    db.commit()
    return {"message": "仓库已删除"}


@router.get("/{warehouse_id}/locations", summary="库位列表")
def list_locations(warehouse_id: int, db: Session = Depends(get_db)):
    w = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="仓库不存在")
    rows = db.query(WarehouseLocation).filter(
        WarehouseLocation.warehouse_id == warehouse_id
    ).order_by(WarehouseLocation.code).all()
    return {"items": [_loc_dict(loc) for loc in rows]}


@router.post("/{warehouse_id}/locations", summary="新建库位（主管/管理员）")
def create_location(warehouse_id: int, data: LocationIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_supervisor)):
    w = db.query(Warehouse).filter(Warehouse.id == warehouse_id).first()
    if not w:
        raise HTTPException(status_code=404, detail="仓库不存在")
    dup = db.query(WarehouseLocation).filter(
        WarehouseLocation.warehouse_id == warehouse_id,
        WarehouseLocation.code == data.code,
    ).first()
    if dup:
        raise HTTPException(status_code=400, detail="该仓库下库位编码已存在")
    loc = WarehouseLocation(warehouse_id=warehouse_id, **data.model_dump())
    db.add(loc)
    db.commit()
    db.refresh(loc)
    return _loc_dict(loc)


@router.put("/locations/{location_id}", summary="修改库位（主管/管理员）")
def update_location(location_id: int, data: LocationIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_supervisor)):
    loc = db.query(WarehouseLocation).filter(WarehouseLocation.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="库位不存在")
    dup = db.query(WarehouseLocation).filter(
        WarehouseLocation.warehouse_id == loc.warehouse_id,
        WarehouseLocation.code == data.code,
        WarehouseLocation.id != location_id,
    ).first()
    if dup:
        raise HTTPException(status_code=400, detail="该仓库下库位编码已存在")
    for k, v in data.model_dump().items():
        setattr(loc, k, v)
    db.commit()
    db.refresh(loc)
    return _loc_dict(loc)


@router.delete("/locations/{location_id}", summary="删除库位（主管/管理员）")
def delete_location(location_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(require_supervisor)):
    loc = db.query(WarehouseLocation).filter(WarehouseLocation.id == location_id).first()
    if not loc:
        raise HTTPException(status_code=404, detail="库位不存在")
    inst = db.query(PartInstance).filter(PartInstance.location_id == location_id).count()
    if inst:
        raise HTTPException(status_code=400,
                            detail=f"该库位还挂着 {inst} 件实物，先移走再删")
    db.delete(loc)
    db.commit()
    return {"message": "库位已删除"}

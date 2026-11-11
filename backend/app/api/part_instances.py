"""备件实例（SN 级）API：登记、装机、拆回、待返厂、报废

与数量层（spare_parts.stock_quantity）的关系：
  - 登记实例时默认同时 +1 库存并记 IN 流水（count_in_stock=true）；
  - 装机默认 -1 库存并记 OUT 流水（deduct_stock=true）；如果这批货已经走过
    领用单扣减，调装机时传 deduct_stock=false，避免扣两次；
  - 拆回入库 +1 并记 RETURN 流水；待返厂/报废不改库存数量（报废从在库状态
    报损时才 -1 并记 ADJUST）。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.device import Device
from app.models.part_instance import PartInstance, PartInstanceStatus
from app.models.spare_part import SparePart
from app.models.user import User
from app.models.warehouse import WarehouseLocation
from app.models.work_order import WorkOrder
from app.services.stock_service import apply_stock_change, available_qty, lock_part

router = APIRouter(tags=["备件实例"], dependencies=[Depends(get_current_user)])


class RegisterIn(BaseModel):
    part_id: int
    sn: Optional[str] = Field(None, max_length=100, description="序列号，散件可空")
    warehouse_id: Optional[int] = None
    location_id: Optional[int] = None
    unit_price: Optional[float] = None
    supplier: Optional[str] = None
    warranty_until: Optional[datetime] = None
    count_in_stock: bool = Field(True, description="是否同时 +1 库存并记入库流水")
    remark: Optional[str] = None


class InstallIn(BaseModel):
    device_id: Optional[int] = None
    device_code: Optional[str] = None
    gpu_index: Optional[int] = None
    work_order_id: Optional[int] = None
    deduct_stock: bool = Field(True, description="是否同时 -1 库存并记出库流水")
    remark: Optional[str] = None


class ReturnIn(BaseModel):
    warehouse_id: Optional[int] = None
    location_id: Optional[int] = None
    work_order_id: Optional[int] = None
    remark: Optional[str] = None


class RmaIn(BaseModel):
    work_order_id: Optional[int] = None
    remark: Optional[str] = None


class ScrapIn(BaseModel):
    remark: Optional[str] = None


def _inst_dict(i: PartInstance) -> dict:
    return {
        "id": i.id, "part_id": i.part_id, "part_code": i.part_code, "part_name": i.part_name,
        "sn": i.sn, "status": i.status,
        "status_label": PartInstanceStatus.LABELS.get(i.status, i.status),
        "warehouse_id": i.warehouse_id, "location_id": i.location_id,
        "location_text": i.location_text,
        "device_id": i.device_id, "device_code": i.device_code, "gpu_index": i.gpu_index,
        "work_order_id": i.work_order_id,
        "unit_price": float(i.unit_price or 0), "supplier": i.supplier,
        "warranty_until": i.warranty_until.isoformat() if i.warranty_until else None,
        "installed_at": i.installed_at.isoformat() if i.installed_at else None,
        "removed_at": i.removed_at.isoformat() if i.removed_at else None,
        "inbound_movement_id": i.inbound_movement_id,
        "outbound_movement_id": i.outbound_movement_id,
        "remark": i.remark,
        "created_at": i.created_at.isoformat() if i.created_at else None,
    }


def _get(db: Session, instance_id: int) -> PartInstance:
    inst = db.query(PartInstance).filter(PartInstance.id == instance_id).first()
    if not inst:
        raise HTTPException(status_code=404, detail="备件实例不存在")
    return inst


def _append_remark(old: Optional[str], text: str) -> str:
    return f"{old}；{text}" if old else text


def _bind_work_order_cost(wo: Optional[WorkOrder], part: SparePart, db: Session) -> None:
    """把这次装机消耗追加工单备件清单并重算成本"""
    if wo is None:
        return
    parts = list(wo.used_parts or [])
    parts.append({
        "name": part.part_name, "code": part.part_code,
        "count": 1, "unit_price": float(part.unit_price or 0),
    })
    wo.used_parts = parts
    try:
        from app.services import sla as sla_service
        sla_service.recompute_cost(wo, db)
    except Exception as e:  # 成本重算失败不影响装机
        logger.warning(f"[PartInstance] 工单成本重算失败: {e}")


@router.get("/", summary="备件实例列表（按 SN / 状态 / 设备 / 备件筛选）")
def list_instances(
    part_id: Optional[int] = None,
    sn: Optional[str] = None,
    status: Optional[str] = None,
    device_code: Optional[str] = None,
    warehouse_id: Optional[int] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(PartInstance)
    if part_id:
        q = q.filter(PartInstance.part_id == part_id)
    if sn:
        q = q.filter(PartInstance.sn.ilike(f"%{sn}%"))
    if status:
        q = q.filter(PartInstance.status == status.upper())
    if device_code:
        q = q.filter(PartInstance.device_code == device_code)
    if warehouse_id:
        q = q.filter(PartInstance.warehouse_id == warehouse_id)
    if keyword:
        q = q.filter(
            PartInstance.sn.ilike(f"%{keyword}%")
            | PartInstance.part_code.ilike(f"%{keyword}%")
            | PartInstance.part_name.ilike(f"%{keyword}%")
            | PartInstance.device_code.ilike(f"%{keyword}%")
        )
    total = q.count()
    rows = (q.order_by(PartInstance.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    from app.models.stock_movement import StockMovement
    ids = [i.inbound_movement_id for i in rows if i.inbound_movement_id]
    mv_map = {m.id: m for m in db.query(StockMovement).filter(StockMovement.id.in_(ids)).all()} if ids else {}
    items = []
    for i in rows:
        d = _inst_dict(i)
        m = mv_map.get(i.inbound_movement_id)
        d["inbound_attachments"] = (m.attachments or []) if m else []
        d["inbound_at"] = m.created_at.isoformat() if m and m.created_at else None
        items.append(d)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@router.get("/summary", summary="某备件的数量账 vs 实例账核对")
def instance_summary(part_id: int, db: Session = Depends(get_db)):
    part = db.query(SparePart).filter(SparePart.id == part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")
    counts = dict(
        db.query(PartInstance.status, func.count(PartInstance.id))
        .filter(PartInstance.part_id == part_id)
        .group_by(PartInstance.status).all()
    )
    in_stock_inst = int(counts.get(PartInstanceStatus.IN_STOCK, 0))
    stock = float(part.stock_quantity or 0)
    return {
        "part_id": part_id, "part_code": part.part_code,
        "stock_quantity": stock,
        "reserved_quantity": float(part.reserved_quantity or 0),
        "available_quantity": available_qty(part),
        "instance_counts": {
            PartInstanceStatus.IN_STOCK: in_stock_inst,
            PartInstanceStatus.INSTALLED: int(counts.get(PartInstanceStatus.INSTALLED, 0)),
            PartInstanceStatus.RMA: int(counts.get(PartInstanceStatus.RMA, 0)),
            PartInstanceStatus.SCRAPPED: int(counts.get(PartInstanceStatus.SCRAPPED, 0)),
        },
        "instance_gap": round(stock - in_stock_inst, 4),
        "gap_hint": "数量账比在库实例多出来的部分＝未登记 SN 的散件" if stock != in_stock_inst else "数量账与在库实例一致",
    }


@router.post("/", summary="登记备件实例（SN 入库）")
def register_instance(data: RegisterIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    part = lock_part(db, data.part_id)
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")

    if data.sn:
        dup = db.query(PartInstance).filter(
            PartInstance.part_id == part.id,
            PartInstance.sn == data.sn,
            PartInstance.status != PartInstanceStatus.SCRAPPED,
        ).first()
        if dup:
            raise HTTPException(status_code=400,
                                detail=f"SN {data.sn} 已登记过（实例 {dup.id}，{PartInstanceStatus.LABELS.get(dup.status)}）")

    loc_text = None
    if data.location_id:
        loc = db.query(WarehouseLocation).filter(WarehouseLocation.id == data.location_id).first()
        if not loc:
            raise HTTPException(status_code=404, detail="库位不存在")
        if data.warehouse_id and loc.warehouse_id != data.warehouse_id:
            raise HTTPException(status_code=400, detail="库位不属于所选仓库")
        data.warehouse_id = data.warehouse_id or loc.warehouse_id
        loc_text = loc.code

    inst = PartInstance(
        part_id=part.id, part_code=part.part_code, part_name=part.part_name,
        sn=data.sn, status=PartInstanceStatus.IN_STOCK,
        warehouse_id=data.warehouse_id, location_id=data.location_id, location_text=loc_text,
        unit_price=data.unit_price if data.unit_price is not None else float(part.unit_price or 0),
        supplier=data.supplier or part.supplier,
        warranty_until=data.warranty_until, remark=data.remark,
    )
    db.add(inst)
    db.flush()

    if data.count_in_stock:
        mv = apply_stock_change(
            db, part, "IN", 1, unit_price=inst.unit_price,
            operator=current_user, remark=f"登记实例 {data.sn or inst.id}",
        )
        inst.inbound_movement_id = mv.id

    db.commit()
    db.refresh(inst)
    logger.info(f"[PartInstance] 登记 {part.part_code} sn={data.sn} 库存 +{1 if data.count_in_stock else 0}")
    return _inst_dict(inst)


@router.post("/{instance_id}/install", summary="装机（绑定设备/工单）")
def install_instance(instance_id: int, data: InstallIn, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    inst = _get(db, instance_id)
    if inst.status != PartInstanceStatus.IN_STOCK:
        raise HTTPException(status_code=400,
                            detail=f"只有「在库」的件才能装机，当前是 {PartInstanceStatus.LABELS.get(inst.status)}")

    dev = None
    if data.device_id:
        dev = db.query(Device).filter(Device.id == data.device_id).first()
    elif data.device_code:
        dev = db.query(Device).filter(Device.device_code == data.device_code).first()
    if not dev:
        raise HTTPException(status_code=404, detail="设备不存在，请先在设备台账里建档（SN 追溯要挂到设备上）")

    wo = None
    if data.work_order_id:
        wo = db.query(WorkOrder).filter(WorkOrder.id == data.work_order_id).first()
        if not wo:
            raise HTTPException(status_code=404, detail="关联工单不存在")

    part = lock_part(db, inst.part_id)
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")

    if not inst.outbound_movement_id:
        # 是否扣库存不看调用方传参，看这件货有没有已经出过库：
        # 走过领用单/直接领用的，出库时已经扣过，装机只是绑设备；没扣过的才在这里扣。
        if available_qty(part) < 1:
            raise HTTPException(
                status_code=400,
                detail=f"可用库存不足：现存 {float(part.stock_quantity or 0):g}，"
                       f"已预占 {float(part.reserved_quantity or 0):g}",
            )
        mv = apply_stock_change(
            db, part, "OUT", -1, unit_price=inst.unit_price,
            work_order_id=data.work_order_id, operator=current_user,
            remark=f"装机 {inst.sn or inst.id} -> {dev.device_code}",
        )
        inst.outbound_movement_id = mv.id
        _bind_work_order_cost(wo, part, db)

    inst.status = PartInstanceStatus.INSTALLED
    inst.device_id = dev.id
    inst.device_code = dev.device_code
    inst.gpu_index = data.gpu_index
    inst.work_order_id = data.work_order_id
    inst.installed_at = datetime.now()
    inst.removed_at = None
    if data.remark:
        inst.remark = _append_remark(inst.remark, data.remark)

    db.commit()
    db.refresh(inst)
    logger.info(f"[PartInstance] 装机 {inst.part_code} sn={inst.sn} -> {dev.device_code}")
    return _inst_dict(inst)


@router.post("/{instance_id}/return-in", summary="拆回入库（回到在库，库存 +1）")
def return_instance(instance_id: int, data: ReturnIn, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    inst = _get(db, instance_id)
    if inst.status not in (PartInstanceStatus.INSTALLED, PartInstanceStatus.RMA):
        raise HTTPException(status_code=400, detail="只有在「已装机/待返厂」的件才能拆回入库")

    part = lock_part(db, inst.part_id)
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")

    loc_text = inst.location_text
    if data.location_id:
        loc = db.query(WarehouseLocation).filter(WarehouseLocation.id == data.location_id).first()
        if not loc:
            raise HTTPException(status_code=404, detail="库位不存在")
        inst.location_id = loc.id
        inst.warehouse_id = loc.warehouse_id
        loc_text = loc.code
    elif data.warehouse_id:
        inst.warehouse_id = data.warehouse_id

    from_device = inst.device_code
    # 只有"这件货确实从库存里扣过"才 +1；在库→待返厂再从待返厂拆回的情况不重复加数
    counted = bool(inst.outbound_movement_id)
    mv = None
    if counted:
        mv = apply_stock_change(
            db, part, "RETURN", 1, unit_price=inst.unit_price,
            work_order_id=data.work_order_id or inst.work_order_id, operator=current_user,
            remark=f"拆回入库 {inst.sn or inst.id}" + (f"（拆自 {from_device}）" if from_device else ""),
        )
        inst.inbound_movement_id = mv.id
    inst.outbound_movement_id = None
    inst.status = PartInstanceStatus.IN_STOCK
    inst.device_id = None
    inst.gpu_index = None
    inst.removed_at = datetime.now()
    inst.location_text = loc_text
    inst.remark = _append_remark(
        inst.remark,
        f"拆自 {from_device}" if from_device else "拆回入库",
    )
    if data.remark:
        inst.remark = _append_remark(inst.remark, data.remark)

    db.commit()
    db.refresh(inst)
    logger.info(f"[PartInstance] 拆回 {inst.part_code} sn={inst.sn}，库存 +{1 if counted else 0}"
                + (f"（流水 {mv.id}）" if mv else ""))
    return _inst_dict(inst)


@router.post("/{instance_id}/rma", summary="标记待返厂（不增减库存）")
def rma_instance(instance_id: int, data: RmaIn, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    inst = _get(db, instance_id)
    if inst.status == PartInstanceStatus.SCRAPPED:
        raise HTTPException(status_code=400, detail="已报废的件不能返厂")
    from_device = inst.device_code
    inst.status = PartInstanceStatus.RMA
    inst.removed_at = datetime.now()
    if data.work_order_id:
        inst.work_order_id = data.work_order_id
    inst.remark = _append_remark(
        inst.remark,
        f"拆自 {from_device}，待返厂" if from_device else "待返厂",
    )
    if data.remark:
        inst.remark = _append_remark(inst.remark, data.remark)
    db.commit()
    db.refresh(inst)
    logger.info(f"[PartInstance] {inst.part_code} sn={inst.sn} 转待返厂")
    try:
        from app.api.notifications import notify_roles
        notify_roles(
            db, ["ADMIN", "SUPERVISOR"], type="PART", title="备件转待返厂（RMA）",
            content=f"{inst.part_code} {inst.part_name} SN={inst.sn or '-'}"
                    + (f"（拆自 {from_device}）" if from_device else "")
                    + f" 已转待返厂，操作人 {current_user.real_name}"
                    + (f"；备注：{data.remark}" if data.remark else ""),
            work_order_id=inst.work_order_id, level="P1", exclude_user_id=current_user.id,
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[PartInstance] RMA 通知失败（忽略）: {e}")
    return _inst_dict(inst)


@router.post("/{instance_id}/scrap", summary="报废")
def scrap_instance(instance_id: int, data: ScrapIn, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    inst = _get(db, instance_id)
    if inst.status == PartInstanceStatus.SCRAPPED:
        raise HTTPException(status_code=400, detail="该件已报废")

    part = lock_part(db, inst.part_id)
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")

    if inst.status == PartInstanceStatus.IN_STOCK:
        # 在库报损：库存要减掉，记 ADJUST（不影响领用成本口径）
        if float(part.stock_quantity or 0) < 1:
            raise HTTPException(status_code=400, detail="库存不足，无法从在库状态报废")
        mv = apply_stock_change(
            db, part, "ADJUST", -1, unit_price=inst.unit_price,
            operator=current_user, remark=f"在库报废 {inst.sn or inst.id}",
        )
        inst.outbound_movement_id = mv.id

    inst.status = PartInstanceStatus.SCRAPPED
    inst.removed_at = inst.removed_at or datetime.now()
    inst.remark = _append_remark(inst.remark, "已报废")
    if data.remark:
        inst.remark = _append_remark(inst.remark, data.remark)
    db.commit()
    db.refresh(inst)
    logger.info(f"[PartInstance] {inst.part_code} sn={inst.sn} 报废")
    try:
        from app.api.notifications import notify_roles
        notify_roles(
            db, ["ADMIN", "SUPERVISOR"], type="PART", title="备件报废",
            content=f"{inst.part_code} {inst.part_name} SN={inst.sn or '-'} 已报废，"
                    f"操作人 {current_user.real_name}"
                    + (f"；原因：{data.remark}" if data.remark else ""),
            work_order_id=inst.work_order_id, level="P1", exclude_user_id=current_user.id,
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[PartInstance] 报废通知失败（忽略）: {e}")
    return _inst_dict(inst)


@router.get("/{instance_id}", summary="备件实例详情")
def get_instance(instance_id: int, db: Session = Depends(get_db)):
    return _inst_dict(_get(db, instance_id))

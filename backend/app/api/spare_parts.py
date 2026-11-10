from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from loguru import logger

from app.core.database import get_db
from app.core.security import get_current_user, require_supervisor
from app.core.notification import notification_service
from app.core.cache_service import cache_service
from app.models.spare_part import SparePart
from app.models.user import User
from app.schemas import SparePartCreate, SparePartUpdate, SparePartResponse, PaginatedResponse
from app.services.stock_service import apply_stock_change, lock_part, normalize_qty

router = APIRouter()


def _sp_to_dict(s: SparePart) -> dict:
    d = {c.name: getattr(s, c.name) for c in s.__table__.columns}
    d["reserved_quantity"] = int(s.reserved_quantity or 0)
    d["available_quantity"] = float(s.stock_quantity or 0) - d["reserved_quantity"]
    return d


def _split_serials(raw: Optional[str]) -> List[str]:
    """把逗号/顿号/分号分隔的 SN 串拆成去重列表（中英文标点都认）"""
    if not raw:
        return []
    out: List[str] = []
    for item in raw.replace("，", ",").replace("、", ",").replace("；", ",").replace(";", ",").split(","):
        s = item.strip()
        if s and s not in out:
            out.append(s)
    return out


# ==================== 进货单导入 Schema ====================
class PurchaseItem(BaseModel):
    part_code: str = Field(..., max_length=50)
    part_name: Optional[str] = None
    specification: Optional[str] = None
    unit: Optional[str] = "个"
    quantity: int = Field(..., gt=0, description="进货数量")
    unit_price: Optional[float] = 0.0
    device_type: Optional[str] = None
    location: Optional[str] = None
    supplier: Optional[str] = None
    safety_stock: Optional[int] = 0


class PurchaseImportRequest(BaseModel):
    items: List[PurchaseItem] = Field(..., min_length=1, max_length=200)


class PurchaseImportResult(BaseModel):
    total: int
    created: int = 0
    updated: int = 0
    skipped: int = 0
    details: List[dict] = []


# ==================== CRUD ====================

@router.get("/", response_model=PaginatedResponse[SparePartResponse], summary="获取备件列表")
def list_spare_parts(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    device_type: Optional[str] = None,
    keyword: Optional[str] = None,
    stock_status: Optional[str] = Query(None, description="sufficient / low_stock / out_of_stock"),
    sort_by: Optional[str] = Query(None, description="stock_quantity / safety_stock / part_code / part_name"),
    sort_order: Optional[str] = Query(None, description="asc / desc"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(SparePart)
    if device_type:
        query = query.filter(SparePart.device_type == device_type)
    if keyword:
        query = query.filter(
            SparePart.part_name.ilike(f"%{keyword}%")
            | SparePart.part_code.ilike(f"%{keyword}%")
            | SparePart.specification.ilike(f"%{keyword}%")
        )
    if stock_status == "sufficient":
        query = query.filter(SparePart.stock_quantity > SparePart.safety_stock)
    elif stock_status == "low_stock":
        query = query.filter(
            SparePart.stock_quantity > 0,
            SparePart.stock_quantity <= SparePart.safety_stock
        )
    elif stock_status == "out_of_stock":
        query = query.filter(SparePart.stock_quantity <= 0)

    total = query.count()
    sort_cols = {
        "stock_quantity": SparePart.stock_quantity,
        "safety_stock": SparePart.safety_stock,
        "part_code": SparePart.part_code,
        "part_name": SparePart.part_name,
    }
    if sort_by in sort_cols:
        col = sort_cols[sort_by]
        query = query.order_by(col.asc() if sort_order == "asc" else col.desc())
    else:
        query = query.order_by(SparePart.id.desc())
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "items": [_sp_to_dict(s) for s in items], "page": page, "page_size": page_size}


@router.get("/alerts", summary="库存预警（带缓存）")
def get_stock_alerts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """获取低库存和缺货预警数据（缓存 30 秒）"""
    cache_key = "stock_alerts:all"
    cached = cache_service.get(cache_key)
    if cached:
        return cached

    low_stock = db.query(SparePart).filter(
        SparePart.stock_quantity > 0,
        SparePart.stock_quantity <= SparePart.safety_stock
    ).all()

    out_of_stock = db.query(SparePart).filter(
        SparePart.stock_quantity <= 0
    ).all()

    result = {
        "low_stock_count": len(low_stock),
        "out_of_stock_count": len(out_of_stock),
        "alert_count": len(low_stock) + len(out_of_stock),
        "low_stock_items": [_sp_to_dict(s) for s in low_stock],
        "out_of_stock_items": [_sp_to_dict(s) for s in out_of_stock],
    }
    cache_service.set(cache_key, result, ttl=30)
    return result


@router.post("/check-alerts", summary="手动触发库存预警检查（管理员/主管）")
def check_stock_alerts(db: Session = Depends(get_db), current_user: User = Depends(require_supervisor)):
    """
    手动触发库存预警检查，发送钉钉通知
    返回预警结果
    """
    from app.core.stock_alert import check_and_notify_stock_alerts
    result = check_and_notify_stock_alerts(db)
    return result


@router.get("/movements", summary="出入库流水（全局，可按备件/工单筛选）")
def list_movements(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    part_id: Optional[int] = None,
    work_order_id: Optional[int] = None,
    movement_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.stock_movement import StockMovement
    q = db.query(StockMovement)
    if part_id:
        q = q.filter(StockMovement.part_id == part_id)
    if work_order_id:
        q = q.filter(StockMovement.work_order_id == work_order_id)
    if movement_type:
        q = q.filter(StockMovement.movement_type == movement_type.upper())
    total = q.count()
    rows = q.order_by(StockMovement.created_at.desc(), StockMovement.id.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_movement_to_dict(m) for m in rows]}


@router.get("/{part_id}", response_model=SparePartResponse, summary="获取备件详情（带缓存）")
def get_spare_part(part_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cache_key = f"spare_part:{part_id}"
    cached = cache_service.get(cache_key)
    if cached:
        return cached

    part = db.query(SparePart).filter(SparePart.id == part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")

    result = _sp_to_dict(part)
    cache_service.set(cache_key, result, ttl=300)
    return result


@router.post("/", response_model=SparePartResponse, summary="创建备件（管理员/主管）")
def create_spare_part(data: SparePartCreate, db: Session = Depends(get_db), current_user: User = Depends(require_supervisor)):
    existing = db.query(SparePart).filter(SparePart.part_code == data.part_code).first()
    if existing:
        raise HTTPException(status_code=400, detail="备件编码已存在")
    payload = data.model_dump()
    # 建备件时录的数量是"期初库存"，不能直接写余额：走入库流水，对账公式才成立
    opening = float(payload.get("stock_quantity") or 0)
    payload["stock_quantity"] = 0
    part = SparePart(**payload)
    db.add(part)
    db.flush()
    if opening > 0:
        apply_stock_change(
            db, part, "IN", opening,
            unit_price=part.unit_price or 0,
            operator=current_user,
            remark="期初库存（建档时录入）",
            source_type="OPENING", source_id=part.id,
        )
    db.commit()
    db.refresh(part)
    cache_service.invalidate_pattern("stock_alerts:*")
    logger.info(f"[SparePart] 新建 {part.part_code}，期初库存 {opening:g}（已记 IN 流水）")
    return part


@router.put("/{part_id}", response_model=SparePartResponse, summary="更新备件（管理员/主管）")
def update_spare_part(part_id: int, data: SparePartUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_supervisor)):
    part = db.query(SparePart).filter(SparePart.id == part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")
    payload = data.model_dump(exclude_unset=True)
    # 库存数量不在这里改：入库/出库/盘点各走各的单据，否则账会断
    payload.pop("stock_quantity", None)
    for key, val in payload.items():
        setattr(part, key, val)
    db.commit()
    db.refresh(part)
    cache_service.delete(f"spare_part:{part_id}")
    cache_service.invalidate_pattern("stock_alerts:*")
    return part


@router.delete("/{part_id}", summary="删除备件（管理员/主管）")
def delete_spare_part(part_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_supervisor)):
    part = db.query(SparePart).filter(SparePart.id == part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")
    # 有实物实例或领用单在引用时不允许删，否则 SN 追溯会断链
    from app.models.part_instance import PartInstance
    from app.models.spare_part_requisition import SparePartRequisition
    inst_cnt = db.query(PartInstance).filter(PartInstance.part_id == part_id).count()
    if inst_cnt:
        raise HTTPException(status_code=400,
                            detail=f"该备件已登记 {inst_cnt} 件实物实例（SN），先处理实物再删")
    req_cnt = db.query(SparePartRequisition).filter(
        SparePartRequisition.part_id == part_id).count()
    if req_cnt:
        raise HTTPException(status_code=400,
                            detail=f"该备件被 {req_cnt} 张领用单引用，不能删除（可把库存改为 0 停用）")
    db.delete(part)
    db.commit()
    cache_service.delete(f"spare_part:{part_id}")
    cache_service.invalidate_pattern("stock_alerts:*")
    return {"message": "备件已删除"}


# ==================== 出入库流水 / 领用消耗 ====================

class ConsumeIn(BaseModel):
    quantity: float = Field(..., gt=0, description="领用数量")
    work_order_id: Optional[int] = Field(None, description="关联工单（领料登记）")
    serial_no: Optional[str] = Field(None, max_length=500, description="本次出库的序列号 SN")
    attachments: Optional[List[str]] = Field(None, description="照片附件 URL")
    remark: Optional[str] = None


class StockInIn(BaseModel):
    quantity: float = Field(..., gt=0, description="入库数量")
    unit_price: Optional[float] = Field(None, description="本次单价，不传则用备件单价")
    serial_no: Optional[str] = Field(None, max_length=500, description="本次入库的序列号 SN")
    attachments: Optional[List[str]] = Field(None, description="照片附件 URL")
    remark: Optional[str] = None


def _movement_to_dict(m) -> dict:
    return {
        "id": m.id,
        "part_id": m.part_id,
        "part_code": m.part_code,
        "part_name": m.part_name,
        "movement_type": m.movement_type,
        "quantity": m.quantity,
        "before_qty": m.before_qty,
        "after_qty": m.after_qty,
        "unit_price": m.unit_price,
        "amount": m.amount,
        "work_order_id": m.work_order_id,
        "operator_name": m.operator_name,
        "serial_no": getattr(m, "serial_no", None),
        "attachments": getattr(m, "attachments", None),
        "remark": m.remark,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


@router.get("/{part_id}/movements", summary="某个备件的出入库流水")
def part_movements(
    part_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.stock_movement import StockMovement
    q = db.query(StockMovement).filter(StockMovement.part_id == part_id)
    total = q.count()
    rows = q.order_by(StockMovement.created_at.desc(), StockMovement.id.desc()) \
            .offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_movement_to_dict(m) for m in rows]}


@router.post("/{part_id}/consume", summary="领用/消耗（仅管理员/主管；维修员走领用审批）")
def consume_part(part_id: int, data: ConsumeIn, db: Session = Depends(get_db),
                 current_user: User = Depends(require_supervisor)):
    from app.models.work_order import WorkOrder
    from app.services import sla as sla_service

    part = lock_part(db, part_id)  # 行锁：并发领用排队，防超卖
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")

    before = float(part.stock_quantity or 0)
    reserved = float(part.reserved_quantity or 0)
    avail = before - reserved
    need_sn = bool(getattr(part, "need_sn", False))
    out_serials = _split_serials(data.serial_no)
    qty_f = float(data.quantity)

    if need_sn:
        if not qty_f.is_integer():
            raise HTTPException(status_code=400, detail="该备件按 SN 管理，出库数量必须是整数")
        if len(out_serials) != int(qty_f):
            raise HTTPException(
                status_code=400,
                detail=f"该备件按 SN 管理：出库 {int(qty_f)} 件要选 {int(qty_f)} 个 SN，"
                       f"当前 {len(out_serials)} 个",
            )
    elif out_serials and len(out_serials) != int(qty_f):
        raise HTTPException(
            status_code=400,
            detail=f"SN 数量（{len(out_serials)} 个）与出库数量（{qty_f:g}）不一致；一个 SN 只能对应一件",
        )

    if data.quantity > avail:
        raise HTTPException(
            status_code=400,
            detail=f"可用库存不足：现存 {before:g}，已预占 {reserved:g}，"
                   f"可用 {avail:g} {part.unit or ''}，本次要领 {data.quantity:g}",
        )

    wo = None
    if data.work_order_id:
        wo = db.query(WorkOrder).filter(WorkOrder.id == data.work_order_id).first()
        if not wo:
            raise HTTPException(status_code=404, detail="关联工单不存在")

    # SN 必须属于本备件且在库：先校验再动库存，避免"库存减了、实物档案没动"
    inst_map = {}
    if out_serials:
        from app.models.part_instance import PartInstance, PartInstanceStatus
        rows = (db.query(PartInstance)
                .filter(PartInstance.part_id == part.id, PartInstance.sn.in_(out_serials))
                .all())
        inst_map = {i.sn: i for i in rows}
        missing = [s for s in out_serials if s not in inst_map]
        if missing:
            raise HTTPException(status_code=400,
                                detail=f"这些 SN 没登记在该备件下：{'、'.join(missing)}")
        not_in_stock = [s for s, i in inst_map.items()
                        if i.status != PartInstanceStatus.IN_STOCK]
        if not_in_stock:
            raise HTTPException(status_code=400,
                                detail=f"这些 SN 不在库（已装机/待返厂/已报废）：{'、'.join(not_in_stock)}")

    mv = apply_stock_change(
        db, part, "OUT", -qty_f, unit_price=part.unit_price or 0,
        work_order_id=data.work_order_id, operator=current_user,
        remark=data.remark,
    )
    mv.serial_no = data.serial_no
    mv.attachments = data.attachments
    db.flush()

    # 按 SN 更新实物实例：有工单且带设备 → 已装机；否则 → 已出库
    for sn, inst in inst_map.items():
        if wo is not None and wo.device_id:
            inst.status = PartInstanceStatus.INSTALLED
            inst.device_id = wo.device_id
            inst.device_code = wo.device_code
            inst.installed_at = datetime.now()
        else:
            inst.status = PartInstanceStatus.ISSUED
            inst.removed_at = datetime.now()
        inst.work_order_id = data.work_order_id
        inst.outbound_movement_id = mv.id

    # 关联工单：把这次领用追加到 used_parts，并重算成本
    if wo is not None:
        parts = list(wo.used_parts or [])
        parts.append({
            "name": part.part_name, "code": part.part_code,
            "count": data.quantity, "unit_price": part.unit_price or 0,
        })
        wo.used_parts = parts
        try:
            sla_service.recompute_cost(wo, db)
        except Exception as e:
            logger.warning(f"[SparePart] 工单成本重算失败: {e}")

    # 同一工单上已审批、还没发料的领用单：这次直接领用就把它冲掉，
    # 否则预占会一直挂着，可用库存永远少一块
    if wo is not None and float(part.reserved_quantity or 0) > 0:
        from app.models.spare_part_requisition import (
            SparePartRequisition, SparePartRequisitionStatus as ReqSt,
        )
        remaining = qty_f
        released = 0.0
        reqs = (db.query(SparePartRequisition)
                .filter(SparePartRequisition.part_id == part.id,
                        SparePartRequisition.status == ReqSt.APPROVED,
                        SparePartRequisition.work_order_id == data.work_order_id)
                .order_by(SparePartRequisition.id)
                .with_for_update()
                .all())
        for req in reqs:
            req_qty = float(req.quantity or 0)
            if remaining < req_qty:
                break
            req.status = ReqSt.ISSUED
            req.issued_at = datetime.now()
            req.movement_id = mv.id
            remaining -= req_qty
            released += req_qty
        if released:
            part.reserved_quantity = normalize_qty(
                max(0.0, float(part.reserved_quantity or 0) - released)
            )
            logger.info(f"[SparePart] 直接领用冲抵领用单 {released:g}，预占降至 {part.reserved_quantity}")

    db.commit()
    db.refresh(mv)
    cache_service.delete(f"spare_part:{part_id}")
    cache_service.invalidate_pattern("stock_alerts:*")
    logger.info(f"[SparePart] 领用 {part.part_code} x{data.quantity}，库存 {before} -> {part.stock_quantity}")
    return {"message": "领用成功", "stock_quantity": float(part.stock_quantity),
            "movement": _movement_to_dict(mv)}


@router.post("/{part_id}/stock-in", summary="入库（管理员/主管）")
def stock_in_part(part_id: int, data: StockInIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_supervisor)):

    part = lock_part(db, part_id)  # 行锁：与领用/盘点串行，避免出入库互相覆盖
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")

    # 按 SN 管理的高价值件：入库必须一物一码，数量与 SN 个数必须对得上
    serials = _split_serials(data.serial_no)
    if getattr(part, "need_sn", False):
        qty = float(data.quantity)
        if not qty.is_integer():
            raise HTTPException(
                status_code=400,
                detail="该备件按 SN 管理，入库数量必须是整数（一物一码，不能填小数）",
            )
        need = int(qty)
        if len(serials) != need:
            raise HTTPException(
                status_code=400,
                detail=f"该备件按 SN 管理：入库 {need} 件要填 {need} 个 SN，"
                       f"当前填了 {len(serials)} 个",
            )

    # SN 数量 / 重复登记先校验，再动库存：数量账和实例账必须同时成立
    if serials and len(serials) != int(float(data.quantity)):
        raise HTTPException(
            status_code=400,
            detail=f"SN 数量（{len(serials)} 个）与入库数量（{float(data.quantity):g}）不一致；一个 SN 只能对应一件",
        )
    if serials:
        from app.models.part_instance import PartInstance
        dup = [r[0] for r in db.query(PartInstance.sn).filter(
            PartInstance.part_id == part.id, PartInstance.sn.in_(serials)).all()]
        if dup:
            raise HTTPException(
                status_code=400,
                detail=f"这些 SN 已经登记过：{'、'.join(dup)}；拆回来的件请走备件实例的「拆回入库」，不要重复登记",
            )

    price = data.unit_price if data.unit_price is not None else (part.unit_price or 0)
    if data.unit_price is not None:
        part.unit_price = data.unit_price

    mv = apply_stock_change(
        db, part, "IN", data.quantity, unit_price=price,
        operator=current_user, remark=data.remark,
    )
    mv.serial_no = data.serial_no
    mv.attachments = data.attachments
    db.flush()
    # 按 SN 生成实物实例（一物一码），库存中心可逐件查看
    if serials:
        from app.models.part_instance import PartInstance, PartInstanceStatus
        for sn in serials:
            db.add(PartInstance(
                part_id=part.id, part_code=part.part_code, part_name=part.part_name,
                sn=sn, status=PartInstanceStatus.IN_STOCK,
                warehouse_id=part.warehouse_id, location_text=part.location,
                unit_price=price, supplier=part.supplier, inbound_movement_id=mv.id,
            ))
    # 库存台账同步：最新 SN + 入库照片（最多留 6 张）
    if data.serial_no:
        part.serial_no = data.serial_no
    if data.attachments:
        merged = list(part.attachments or []) + list(data.attachments)
        part.attachments = merged[-6:]
    db.commit()
    db.refresh(mv)
    cache_service.delete(f"spare_part:{part_id}")
    cache_service.invalidate_pattern("stock_alerts:*")
    return {"message": "入库成功", "stock_quantity": float(part.stock_quantity),
            "movement": _movement_to_dict(mv)}


# ==================== 进货单批量导入 ====================

@router.post("/import", response_model=PurchaseImportResult, summary="进货单批量导入（管理员/主管）")
def import_purchase_orders(req: PurchaseImportRequest, db: Session = Depends(get_db), current_user: User = Depends(require_supervisor)):
    """
    批量导入备件：
    - 新备件（编码不存在）→ 自动创建
    - 已有备件（编码存在）→ 累加库存数量，更新单价和供应商
    """
    result = PurchaseImportResult(total=len(req.items))
    details = []

    for item in req.items:
        existing = db.query(SparePart).filter(SparePart.part_code == item.part_code).first()

        # 按 SN 管理的件不能走批量导入（会变成"有数量没实物档案"），引导到入库页逐件登记
        if existing is not None and getattr(existing, "need_sn", False):
            result.skipped += 1
            details.append({
                "part_code": item.part_code,
                "action": "skipped",
                "reason": "该件按 SN 管理，请走「备件入库」页逐件登记 SN",
            })
            continue

        if existing:
            # 已有备件：累加库存（走统一入口记流水，不做裸改数字）
            part = lock_part(db, existing.id) or existing
            price = (item.unit_price if item.unit_price and item.unit_price > 0
                     else (part.unit_price or 0))
            apply_stock_change(db, part, "IN", item.quantity, unit_price=price,
                               operator=current_user, remark=f"进货单批量导入（{item.part_code}）")
            if item.unit_price and item.unit_price > 0:
                part.unit_price = item.unit_price
            if item.supplier:
                part.supplier = item.supplier
            if item.location:
                part.location = item.location
            if item.safety_stock > 0:
                part.safety_stock = item.safety_stock
            if item.part_name and not part.part_name:
                part.part_name = item.part_name
            if item.specification and not part.specification:
                part.specification = item.specification
            result.updated += 1
            details.append({
                "part_code": item.part_code,
                "action": "updated",
                "quantity_added": item.quantity,
                "new_stock": float(part.stock_quantity or 0),
            })
        else:
            # 新备件：先建 0 库存，再记一条期初入库流水
            part = SparePart(
                part_code=item.part_code,
                part_name=item.part_name or item.part_code,
                specification=item.specification,
                unit=item.unit or "个",
                stock_quantity=0,
                safety_stock=item.safety_stock or 0,
                unit_price=item.unit_price or 0,
                device_type=item.device_type,
                location=item.location,
                supplier=item.supplier,
            )
            db.add(part)
            db.flush()
            apply_stock_change(db, part, "IN", item.quantity, unit_price=item.unit_price or 0,
                               operator=current_user, remark="进货单批量导入（新建备件期初）",
                               source_type="OPENING", source_id=part.id)
            result.created += 1
            details.append({
                "part_code": item.part_code,
                "action": "created",
                "quantity": item.quantity,
            })

    db.commit()
    cache_service.invalidate_pattern("stock_alerts:*")
    logger.info(f"[SpareParts] 进货单导入完成: 共{result.total}项, 新建{result.created}, 更新{result.updated}")
    result.details = details
    return result

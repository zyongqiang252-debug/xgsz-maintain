from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional, List
from loguru import logger

from app.core.database import get_db
from app.core.security import get_current_user, require_supervisor
from app.core.notification import notification_service
from app.core.cache_service import cache_service
from app.models.spare_part import SparePart
from app.models.user import User
from app.schemas import SparePartCreate, SparePartUpdate, SparePartResponse, PaginatedResponse
from app.services.stock_service import lock_part

router = APIRouter()


def _sp_to_dict(s: SparePart) -> dict:
    d = {c.name: getattr(s, c.name) for c in s.__table__.columns}
    d["reserved_quantity"] = int(s.reserved_quantity or 0)
    d["available_quantity"] = float(s.stock_quantity or 0) - d["reserved_quantity"]
    return d


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
    part = SparePart(**data.model_dump())
    db.add(part)
    db.commit()
    db.refresh(part)
    cache_service.invalidate_pattern("stock_alerts:*")
    return part


@router.put("/{part_id}", response_model=SparePartResponse, summary="更新备件（管理员/主管）")
def update_spare_part(part_id: int, data: SparePartUpdate, db: Session = Depends(get_db), current_user: User = Depends(require_supervisor)):
    part = db.query(SparePart).filter(SparePart.id == part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")
    for key, val in data.model_dump(exclude_unset=True).items():
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


@router.post("/{part_id}/consume", summary="领用/消耗（维修员可用，自动扣库存并记流水）")
def consume_part(part_id: int, data: ConsumeIn, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    from app.models.stock_movement import StockMovement
    from app.models.work_order import WorkOrder
    from app.services import sla as sla_service

    part = lock_part(db, part_id)  # 行锁：并发领用排队，防超卖
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")

    before = float(part.stock_quantity or 0)
    reserved = float(part.reserved_quantity or 0)
    avail = before - reserved
    if data.quantity > avail:
        raise HTTPException(
            status_code=400,
            detail=f"可用库存不足：现存 {before:g}，已预占 {reserved:g}，"
                   f"可用 {avail:g} {part.unit or ''}，本次要领 {data.quantity:g}",
        )
    after = before - data.quantity
    part.stock_quantity = int(after) if float(after).is_integer() else after

    wo = None
    if data.work_order_id:
        wo = db.query(WorkOrder).filter(WorkOrder.id == data.work_order_id).first()
        if not wo:
            raise HTTPException(status_code=404, detail="关联工单不存在")

    mv = StockMovement(
        part_id=part.id, part_code=part.part_code, part_name=part.part_name,
        movement_type="OUT", quantity=data.quantity,
        before_qty=before, after_qty=after,
        unit_price=part.unit_price or 0,
        amount=round((part.unit_price or 0) * data.quantity, 2),
        work_order_id=data.work_order_id,
        operator_id=current_user.id, operator_name=current_user.real_name,
        serial_no=data.serial_no, attachments=data.attachments,
        remark=data.remark,
    )
    db.add(mv)

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

    db.commit()
    db.refresh(mv)
    cache_service.delete(f"spare_part:{part_id}")
    cache_service.invalidate_pattern("stock_alerts:*")
    logger.info(f"[SparePart] 领用 {part.part_code} x{data.quantity}，库存 {before} -> {after}")
    return {"message": "领用成功", "stock_quantity": float(part.stock_quantity),
            "movement": _movement_to_dict(mv)}


@router.post("/{part_id}/stock-in", summary="入库（管理员/主管）")
def stock_in_part(part_id: int, data: StockInIn, db: Session = Depends(get_db),
                  current_user: User = Depends(require_supervisor)):
    from app.models.stock_movement import StockMovement

    part = lock_part(db, part_id)  # 行锁：与领用/盘点串行，避免出入库互相覆盖
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")

    before = float(part.stock_quantity or 0)
    after = before + data.quantity
    part.stock_quantity = int(after) if float(after).is_integer() else after
    price = data.unit_price if data.unit_price is not None else (part.unit_price or 0)
    if data.unit_price is not None:
        part.unit_price = data.unit_price

    mv = StockMovement(
        part_id=part.id, part_code=part.part_code, part_name=part.part_name,
        movement_type="IN", quantity=data.quantity,
        before_qty=before, after_qty=after,
        unit_price=price, amount=round(price * data.quantity, 2),
        operator_id=current_user.id, operator_name=current_user.real_name,
        serial_no=data.serial_no, attachments=data.attachments,
        remark=data.remark,
    )
    db.add(mv)
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

        if existing:
            # 已有备件：累加库存
            existing.stock_quantity += item.quantity
            if item.unit_price and item.unit_price > 0:
                existing.unit_price = item.unit_price
            if item.supplier:
                existing.supplier = item.supplier
            if item.location:
                existing.location = item.location
            if item.safety_stock > 0:
                existing.safety_stock = item.safety_stock
            if item.part_name and not existing.part_name:
                existing.part_name = item.part_name
            if item.specification and not existing.specification:
                existing.specification = item.specification
            result.updated += 1
            details.append({
                "part_code": item.part_code,
                "action": "updated",
                "quantity_added": item.quantity,
                "new_stock": existing.stock_quantity,
            })
        else:
            # 新备件：创建
            part = SparePart(
                part_code=item.part_code,
                part_name=item.part_name or item.part_code,
                specification=item.specification,
                unit=item.unit or "个",
                stock_quantity=item.quantity,
                safety_stock=item.safety_stock or 0,
                unit_price=item.unit_price or 0,
                device_type=item.device_type,
                location=item.location,
                supplier=item.supplier,
            )
            db.add(part)
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

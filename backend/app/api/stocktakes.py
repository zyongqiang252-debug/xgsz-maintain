"""盘点 API：建单 → 录实盘数 → 提交 → 审批（差异改库存并记 ADJUST 流水）

关键点：
  - 建单时把账面数量快照进 stocktake_items.system_qty，后面即使有人领用、
    也不影响这张单的口径（否则永远盘不平）；
  - 审批时才改库存，且逐项生成 ADJUST 流水（可正可负），相当于"红冲"；
  - 差异金额 = (实盘 - 账面) × 单价，正数盘盈、负数盘亏。
"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_supervisor
from app.models.spare_part import SparePart
from app.models.stocktake import Stocktake, StocktakeItem, StocktakeStatus
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.stock_service import apply_stock_change, lock_part, normalize_qty

router = APIRouter(tags=["库存盘点"], dependencies=[Depends(get_current_user)])


class CreateIn(BaseModel):
    warehouse_id: Optional[int] = Field(None, description="盘哪个仓；空=全部")
    device_type: Optional[str] = Field(None, description="只盘某类设备的备件")
    keyword: Optional[str] = Field(None, description="按编码/名称过滤盘点范围")
    include_unassigned: bool = Field(True, description="是否包含未归仓的备件")
    remark: Optional[str] = None


class CountItem(BaseModel):
    item_id: int
    actual_qty: float = Field(..., ge=0)
    reason: Optional[str] = None


class CountIn(BaseModel):
    items: List[CountItem] = Field(..., min_length=1, max_length=500)


class ApproveIn(BaseModel):
    remark: Optional[str] = None


def _take_dict(t: Stocktake, with_items: bool = False, db: Optional[Session] = None) -> dict:
    d = {
        "id": t.id, "take_no": t.take_no,
        "warehouse_id": t.warehouse_id, "warehouse_name": t.warehouse_name,
        "status": t.status, "status_label": StocktakeStatus.LABELS.get(t.status, t.status),
        "item_count": t.item_count, "counted_count": t.counted_count,
        "diff_count": t.diff_count, "diff_amount": round(float(t.diff_amount or 0), 2),
        "created_by_name": t.created_by_name,
        "submitted_at": t.submitted_at.isoformat() if t.submitted_at else None,
        "approved_by_name": t.approved_by_name,
        "approved_at": t.approved_at.isoformat() if t.approved_at else None,
        "remark": t.remark,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }
    if with_items and db is not None:
        items = (db.query(StocktakeItem)
                 .filter(StocktakeItem.stocktake_id == t.id)
                 .order_by(StocktakeItem.part_code).all())
        d["items"] = [_item_dict(i) for i in items]
    return d


def _item_dict(i: StocktakeItem) -> dict:
    return {
        "id": i.id, "part_id": i.part_id, "part_code": i.part_code,
        "part_name": i.part_name, "unit": i.unit, "location_text": i.location_text,
        "system_qty": float(i.system_qty or 0),
        "actual_qty": None if i.actual_qty is None else float(i.actual_qty),
        "diff_qty": None if i.diff_qty is None else float(i.diff_qty),
        "unit_price": float(i.unit_price or 0),
        "diff_amount": round(float(i.diff_amount or 0), 2),
        "reason": i.reason, "movement_id": i.movement_id,
    }


def _recalc(t: Stocktake, db: Session) -> None:
    items = db.query(StocktakeItem).filter(StocktakeItem.stocktake_id == t.id).all()
    t.item_count = len(items)
    t.counted_count = sum(1 for i in items if i.actual_qty is not None)
    t.diff_count = sum(1 for i in items if i.diff_qty not in (None, 0))
    t.diff_amount = round(sum(float(i.diff_amount or 0) for i in items), 2)


def _gen_no(db: Session) -> str:
    base = f"PD-{datetime.now():%Y%m%d%H%M%S}"
    no, n = base, 1
    while db.query(Stocktake).filter(Stocktake.take_no == no).first():
        n += 1
        no = f"{base}-{n}"
    return no


@router.post("/", summary="新建盘点单（生成账面快照）")
def create_stocktake(data: CreateIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_supervisor)):
    wh = None
    if data.warehouse_id:
        wh = db.query(Warehouse).filter(Warehouse.id == data.warehouse_id).first()
        if not wh:
            raise HTTPException(status_code=404, detail="仓库不存在")

    q = db.query(SparePart)
    if data.warehouse_id:
        if data.include_unassigned:
            q = q.filter(
                (SparePart.warehouse_id == data.warehouse_id)
                | (SparePart.warehouse_id.is_(None))
            )
        else:
            q = q.filter(SparePart.warehouse_id == data.warehouse_id)
    if data.device_type:
        q = q.filter(SparePart.device_type == data.device_type)
    if data.keyword:
        q = q.filter(
            SparePart.part_code.ilike(f"%{data.keyword}%")
            | SparePart.part_name.ilike(f"%{data.keyword}%")
        )
    parts = q.order_by(SparePart.part_code).all()
    if not parts:
        raise HTTPException(status_code=400, detail="盘点范围里没有备件，检查仓库/设备类型/关键词")

    take = Stocktake(
        take_no=_gen_no(db),
        warehouse_id=data.warehouse_id,
        warehouse_name=wh.name if wh else "全部仓库",
        status=StocktakeStatus.DRAFT,
        created_by=current_user.id, created_by_name=current_user.real_name,
        remark=data.remark,
    )
    db.add(take)
    db.flush()

    for p in parts:
        db.add(StocktakeItem(
            stocktake_id=take.id, part_id=p.id, part_code=p.part_code,
            part_name=p.part_name, unit=p.unit, location_text=p.location,
            system_qty=float(p.stock_quantity or 0),
            unit_price=float(p.unit_price or 0),
        ))
    db.flush()
    _recalc(take, db)
    db.commit()
    db.refresh(take)
    logger.info(f"[Stocktake] 新建 {take.take_no}，条目 {take.item_count}")
    return _take_dict(take)


@router.get("/", summary="盘点单列表")
def list_stocktakes(
    status: Optional[str] = None,
    warehouse_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(Stocktake)
    if status:
        q = q.filter(Stocktake.status == status.upper())
    if warehouse_id:
        q = q.filter(Stocktake.warehouse_id == warehouse_id)
    total = q.count()
    rows = (q.order_by(Stocktake.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_take_dict(t) for t in rows]}


@router.get("/{take_id}", summary="盘点单详情（含明细）")
def get_stocktake(take_id: int, db: Session = Depends(get_db)):
    t = db.query(Stocktake).filter(Stocktake.id == take_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="盘点单不存在")
    return _take_dict(t, with_items=True, db=db)


@router.post("/{take_id}/count", summary="录入实盘数（可多次、可只录一部分）")
def count_stocktake(take_id: int, data: CountIn, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    t = db.query(Stocktake).filter(Stocktake.id == take_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="盘点单不存在")
    if t.status not in (StocktakeStatus.DRAFT, StocktakeStatus.COUNTING):
        raise HTTPException(status_code=400,
                            detail=f"当前状态「{StocktakeStatus.LABELS.get(t.status)}」不能录数")

    ids = [c.item_id for c in data.items]
    items = {i.id: i for i in db.query(StocktakeItem).filter(
        StocktakeItem.stocktake_id == t.id, StocktakeItem.id.in_(ids)
    ).all()}
    missing = [str(i) for i in ids if i not in items]
    if missing:
        raise HTTPException(status_code=400, detail=f"明细不属于本单：{','.join(missing)}")

    for c in data.items:
        item = items[c.item_id]
        item.actual_qty = normalize_qty(c.actual_qty)
        item.diff_qty = normalize_qty(float(c.actual_qty) - float(item.system_qty or 0))
        item.diff_amount = round(float(item.diff_qty) * float(item.unit_price or 0), 2)
        if c.reason:
            item.reason = c.reason

    if t.status == StocktakeStatus.DRAFT:
        t.status = StocktakeStatus.COUNTING
    _recalc(t, db)
    db.commit()
    db.refresh(t)
    return _take_dict(t, with_items=False)


@router.post("/{take_id}/submit", summary="提交盘点单（要求全部录完）")
def submit_stocktake(take_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    t = db.query(Stocktake).filter(Stocktake.id == take_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="盘点单不存在")
    if t.status not in (StocktakeStatus.DRAFT, StocktakeStatus.COUNTING):
        raise HTTPException(status_code=400, detail="只有草稿/盘点中的单子能提交")

    uncounted = db.query(func.count(StocktakeItem.id)).filter(
        StocktakeItem.stocktake_id == t.id, StocktakeItem.actual_qty.is_(None)
    ).scalar() or 0
    if uncounted:
        raise HTTPException(status_code=400,
                            detail=f"还有 {uncounted} 项没录实盘数，先录完再提交")

    t.status = StocktakeStatus.SUBMITTED
    t.submitted_at = datetime.now()
    _recalc(t, db)
    db.commit()
    db.refresh(t)
    logger.info(f"[Stocktake] {t.take_no} 提交，差异 {t.diff_count} 项 / {t.diff_amount:g} 元")

    try:
        from app.api.notifications import notify_roles
        notify_roles(
            db, ["ADMIN", "SUPERVISOR"], type="STOCKTAKE", title="盘点单待审批",
            content=f"{current_user.real_name} 提交了盘点单 {t.take_no}（仓库 {t.warehouse_name or '-'}），"
                    f"差异 {t.diff_count} 项、金额 {t.diff_amount:g} 元，请及时审批",
            level="P2", exclude_user_id=current_user.id,
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[Stocktake] 提交通知失败（忽略）: {e}")
    return _take_dict(t)


@router.post("/{take_id}/approve", summary="审批盘点单（差异改库存并记 ADJUST 流水）")
def approve_stocktake(take_id: int, data: ApproveIn, db: Session = Depends(get_db),
                      current_user: User = Depends(require_supervisor)):
    t = db.query(Stocktake).filter(Stocktake.id == take_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="盘点单不存在")
    if t.status != StocktakeStatus.SUBMITTED:
        raise HTTPException(status_code=400, detail="只有「待审批」的单子能审批")

    items = (db.query(StocktakeItem)
             .filter(StocktakeItem.stocktake_id == t.id).order_by(StocktakeItem.id).all())
    changed = 0
    for item in items:
        if item.diff_qty in (None, 0):
            continue
        part = lock_part(db, item.part_id)
        if not part:
            logger.warning(f"[Stocktake] {t.take_no} 明细 {item.id} 的备件已删除，跳过")
            continue
        mv = apply_stock_change(
            db, part, "ADJUST", 0, unit_price=item.unit_price,
            operator=current_user, set_to=float(item.actual_qty),
            remark=f"盘点 {t.take_no} 差异调整（账面 {float(item.system_qty):g} → 实盘 {float(item.actual_qty):g}）",
            source_type="STOCKTAKE", source_id=t.id,
        )
        item.movement_id = mv.id
        # 盘亏后预占可能超过库存，夹一下，否则"可用库存"会变负数
        if float(part.reserved_quantity or 0) > float(part.stock_quantity or 0):
            logger.warning(
                f"[Stocktake] {part.part_code} 盘亏后预占 {part.reserved_quantity} 超出库存 "
                f"{part.stock_quantity}，自动下调预占"
            )
            part.reserved_quantity = normalize_qty(float(part.stock_quantity or 0))
        changed += 1

    if data.remark:
        t.remark = f"{t.remark}；{data.remark}" if t.remark else data.remark
    t.status = StocktakeStatus.APPROVED
    t.approved_by = current_user.id
    t.approved_by_name = current_user.real_name
    t.approved_at = datetime.now()
    _recalc(t, db)
    db.commit()
    db.refresh(t)
    logger.info(f"[Stocktake] {t.take_no} 审批通过，调整 {changed} 项，金额 {t.diff_amount:g}")

    try:
        from app.api.notifications import notify_user
        notify_user(
            db, t.created_by, type="STOCKTAKE", title="盘点结果已确认",
            content=f"盘点单 {t.take_no} 已审批通过：调整 {changed} 项、差异金额 {t.diff_amount:g} 元"
                    f"（审批人：{current_user.real_name}）",
            level="P2", exclude_user_id=current_user.id,
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[Stocktake] 审批通知失败（忽略）: {e}")
    return {**_take_dict(t), "adjusted_items": changed}


@router.post("/{take_id}/cancel", summary="作废盘点单")
def cancel_stocktake(take_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(require_supervisor)):
    t = db.query(Stocktake).filter(Stocktake.id == take_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="盘点单不存在")
    if t.status == StocktakeStatus.APPROVED:
        raise HTTPException(status_code=400, detail="已审批的单子不能作废（库存已调整，需走反向单据）")
    t.status = StocktakeStatus.CANCELLED
    db.commit()
    try:
        from app.api.notifications import notify_user
        notify_user(
            db, t.created_by, type="STOCKTAKE", title="盘点单已作废",
            content=f"盘点单 {t.take_no} 已被 {current_user.real_name} 作废，无需继续盘点",
            level="P3", exclude_user_id=current_user.id,
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[Stocktake] 作废通知失败（忽略）: {e}")
    return _take_dict(t)

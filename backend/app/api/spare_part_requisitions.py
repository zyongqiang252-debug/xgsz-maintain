"""备件领用审批 API：申请 → 审批（预占库存）→ 出库（扣减并释放预占）

为什么要预占（reserved_quantity）：
  原来审批通过不动库存，两个维修员同时申请最后一块 GPU 卡，两张单都能批，
  第二个人去出库才发现没货。现在审批通过就把数量"占住"：
      可用库存 = 现存 - 预占
  审批时按可用库存校验，出库时才真正扣现存并释放预占。
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.cache_service import cache_service
from app.core.database import get_db
from app.core.security import get_current_user, require_supervisor
from app.models.spare_part import SparePart
from app.models.spare_part_requisition import (
    SparePartRequisition, SparePartRequisitionStatus as St,
)
from app.models.user import User
from app.models.work_order import WorkOrder
from app.services.stock_service import apply_stock_change, available_qty, lock_part, normalize_qty

router = APIRouter(tags=["备件领用"], dependencies=[Depends(get_current_user)])


class RequisitionIn(BaseModel):
    part_id: int
    quantity: float = Field(..., gt=0, description="申请领用数量")
    work_order_id: Optional[int] = None
    reason: Optional[str] = None


class RejectIn(BaseModel):
    reject_reason: str = Field(..., min_length=2, max_length=500)


class IssueIn(BaseModel):
    remark: Optional[str] = None


def _req_dict(r: SparePartRequisition, part: Optional[SparePart] = None) -> dict:
    d = {
        "id": r.id, "part_id": r.part_id, "part_code": r.part_code, "part_name": r.part_name,
        "quantity": float(r.quantity or 0), "unit": r.unit,
        "work_order_id": r.work_order_id, "reason": r.reason,
        "status": r.status,
        "status_label": {
            St.PENDING: "待审批", St.APPROVED: "已批准（已预占）",
            St.REJECTED: "已驳回", St.CANCELLED: "已撤销", St.ISSUED: "已出库",
        }.get(r.status, r.status),
        "applicant_id": r.applicant_id, "applicant_name": r.applicant_name,
        "approver_name": r.approver_name,
        "approved_at": r.approved_at.isoformat() if r.approved_at else None,
        "reject_reason": r.reject_reason,
        "movement_id": r.movement_id,
        "issued_at": r.issued_at.isoformat() if r.issued_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }
    if part is not None:
        d["stock_quantity"] = float(part.stock_quantity or 0)
        d["reserved_quantity"] = float(part.reserved_quantity or 0)
        d["available_quantity"] = available_qty(part)
    return d


def _get(db: Session, rid: int) -> SparePartRequisition:
    r = db.query(SparePartRequisition).filter(SparePartRequisition.id == rid).first()
    if not r:
        raise HTTPException(status_code=404, detail="领用申请不存在")
    return r


@router.post("/", summary="提交备件领用申请")
def create_requisition(data: RequisitionIn, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    part = db.query(SparePart).filter(SparePart.id == data.part_id).first()
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")
    if data.work_order_id:
        if not db.query(WorkOrder).filter(WorkOrder.id == data.work_order_id).first():
            raise HTTPException(status_code=404, detail="关联工单不存在")
    # 技术员领用必须关联工单，否则这笔备件成本无法落到任何维修单上
    role = (getattr(current_user.role, "value", current_user.role) or "").upper()
    if role == "TECHNICIAN" and not data.work_order_id:
        raise HTTPException(status_code=400, detail="技术员领用备件必须关联工单，否则无法计入维修成本")

    r = SparePartRequisition(
        part_id=part.id, part_code=part.part_code, part_name=part.part_name,
        quantity=data.quantity, unit=part.unit, work_order_id=data.work_order_id,
        reason=data.reason, status=St.PENDING,
        applicant_id=current_user.id, applicant_name=current_user.real_name,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    logger.info(f"[Requisition] {current_user.real_name} 申请 {part.part_code} x{data.quantity:g}")

    # 通知审批人：有单待批（申请人自己不发）
    try:
        from app.api.notifications import notify_roles
        wo_txt = f"，关联工单 #{r.work_order_id}" if r.work_order_id else ""
        notify_roles(
            db, ["ADMIN", "SUPERVISOR"], type="REQUISITION", title="备件领用待审批",
            content=f"{current_user.real_name} 申请领用 {part.part_code} {part.part_name} "
                    f"x{data.quantity:g}{part.unit or ''}{wo_txt}；事由：{data.reason or '未填写'}",
            level="P2", exclude_user_id=current_user.id,
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[Requisition] 待审批通知失败（忽略）: {e}")
    return _req_dict(r, part)


@router.get("/", summary="领用申请列表（mine=true 只看自己的）")
def list_requisitions(
    status: Optional[str] = None,
    mine: bool = False,
    work_order_id: Optional[int] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(SparePartRequisition)
    if status:
        q = q.filter(SparePartRequisition.status == status.upper())
    if mine:
        q = q.filter(SparePartRequisition.applicant_id == current_user.id)
    if work_order_id:
        q = q.filter(SparePartRequisition.work_order_id == work_order_id)
    total = q.count()
    rows = (q.order_by(SparePartRequisition.id.desc())
            .offset((page - 1) * page_size).limit(page_size).all())
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_req_dict(r) for r in rows]}


@router.get("/{rid}", summary="领用申请详情")
def get_requisition(rid: int, db: Session = Depends(get_db)):
    r = _get(db, rid)
    part = db.query(SparePart).filter(SparePart.id == r.part_id).first()
    return _req_dict(r, part)


@router.post("/{rid}/approve", summary="审批通过（预占库存，主管/管理员）")
def approve_requisition(rid: int, db: Session = Depends(get_db),
                        current_user: User = Depends(require_supervisor)):
    r = _get(db, rid)
    if r.status != St.PENDING:
        raise HTTPException(status_code=400,
                            detail=f"当前状态「{_req_dict(r)['status_label']}」不能审批")

    part = lock_part(db, r.part_id)
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")

    qty = float(r.quantity or 0)
    avail = available_qty(part)
    if qty > avail:
        raise HTTPException(
            status_code=400,
            detail=f"可用库存不足：现存 {float(part.stock_quantity or 0):g}，"
                   f"已预占 {float(part.reserved_quantity or 0):g}，"
                   f"可用 {avail:g}，本次申请 {qty:g}",
        )

    part.reserved_quantity = normalize_qty(float(part.reserved_quantity or 0) + qty)
    r.status = St.APPROVED
    r.approver_id = current_user.id
    r.approver_name = current_user.real_name
    r.approved_at = datetime.now()
    db.commit()
    db.refresh(r)
    cache_service.invalidate_pattern("stock_alerts:*")
    cache_service.delete(f"spare_part:{part.id}")
    logger.info(f"[Requisition] {rid} 审批通过，预占 {part.part_code} {qty:g}（预占合计 {part.reserved_quantity}）")

    try:
        from app.api.notifications import notify_user
        notify_user(
            db, r.applicant_id, type="REQUISITION", title="领用申请已批准",
            content=f"你申请的 {part.part_code} {part.part_name} x{qty:g}{part.unit or ''} 已批准，"
                    f"请到仓库领料（审批人：{current_user.real_name}）",
            level="P2", exclude_user_id=current_user.id,
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[Requisition] 批准通知失败（忽略）: {e}")
    return _req_dict(r, part)


@router.post("/{rid}/reject", summary="驳回（主管/管理员）")
def reject_requisition(rid: int, data: RejectIn, db: Session = Depends(get_db),
                       current_user: User = Depends(require_supervisor)):
    r = _get(db, rid)
    if r.status not in (St.PENDING, St.APPROVED):
        raise HTTPException(status_code=400, detail="该申请已出库/已撤销，不能驳回")

    part = lock_part(db, r.part_id)
    if r.status == St.APPROVED and part:  # 已预占的要释放
        part.reserved_quantity = normalize_qty(
            max(0.0, float(part.reserved_quantity or 0) - float(r.quantity or 0))
        )

    r.status = St.REJECTED
    r.reject_reason = data.reject_reason
    r.approver_id = current_user.id
    r.approver_name = current_user.real_name
    r.approved_at = datetime.now()
    db.commit()
    db.refresh(r)
    cache_service.invalidate_pattern("stock_alerts:*")
    if part is not None:
        cache_service.delete(f"spare_part:{part.id}")

    try:
        from app.api.notifications import notify_user
        notify_user(
            db, r.applicant_id, type="REQUISITION", title="领用申请被驳回",
            content=f"你申请领用 {r.part_code} {r.part_name} x{float(r.quantity or 0):g} 被驳回，"
                    f"原因：{data.reject_reason}",
            level="P2", exclude_user_id=current_user.id,
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[Requisition] 驳回通知失败（忽略）: {e}")
    return _req_dict(r, part)


@router.post("/{rid}/issue", summary="领料/发料出库（审批人代发，或申请人本人自助领料）")
def issue_requisition(rid: int, data: IssueIn, db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    r = _get(db, rid)

    # 谁能发料：主管/管理员可以代发任意单；申请人本人可以给自己的单领料
    _role = getattr(current_user.role, "value", current_user.role)
    _is_supervisor = _role in ("ADMIN", "SUPERVISOR")
    if not (_is_supervisor or r.applicant_id == current_user.id):
        raise HTTPException(
            status_code=403,
            detail="只有申请人本人或主管/管理员可以领料出库",
        )

    if r.movement_id:
        raise HTTPException(status_code=400, detail="该领用单已出库，请勿重复提交")
    if r.status != St.APPROVED:
        raise HTTPException(
            status_code=400,
            detail=f"当前状态「{_req_dict(r)['status_label']}」不能出库：审批只预占库存，发料才扣减，请先审批通过",
        )

    part = lock_part(db, r.part_id)
    if not part:
        raise HTTPException(status_code=404, detail="备件不存在")

    qty = float(r.quantity or 0)
    stock = float(part.stock_quantity or 0)
    reserved = float(part.reserved_quantity or 0)
    if qty > stock:
        raise HTTPException(status_code=400,
                            detail=f"库存不足：现存 {stock:g}，本次出库 {qty:g}")
    # 只释放本单自己占的那份；预占不足说明单子没占够（或被盘点下调），别去动别人的预占
    if reserved < qty:
        raise HTTPException(
            status_code=400,
            detail=f"预占与单据不一致：{part.part_code} 当前预占 {reserved:g}，本单需要 {qty:g}；"
                   f"请驳回后重新申请审批",
        )

    # 按 SN 管理的件：出库必须同时把实物实例划走，否则数量账和实例账会对不上
    insts = []
    if getattr(part, "need_sn", False):
        from app.models.part_instance import PartInstance, PartInstanceStatus
        if not qty.is_integer():
            raise HTTPException(status_code=400, detail="该备件按 SN 管理，出库数量必须是整数")
        insts = (db.query(PartInstance)
                 .filter(PartInstance.part_id == part.id,
                         PartInstance.status == PartInstanceStatus.IN_STOCK)
                 .order_by(PartInstance.id)
                 .limit(int(qty))
                 .with_for_update()
                 .all())
        if len(insts) < int(qty):
            raise HTTPException(
                status_code=400,
                detail=f"该备件按 SN 管理：要出 {int(qty)} 件，但在库实例只有 {len(insts)} 个",
            )

    wo = None
    if r.work_order_id:
        wo = db.query(WorkOrder).filter(WorkOrder.id == r.work_order_id).first()

    # 成本价按实际发出的 SN 实例入库单价加权；非 SN 件/实例无价时退回台账单价
    billing_price = float(part.unit_price or 0)
    if insts:
        prices = [float(i.unit_price or part.unit_price or 0) for i in insts]
        if prices:
            billing_price = sum(prices) / len(prices)

    mv = apply_stock_change(
        db, part, "OUT", -qty, unit_price=billing_price,
        work_order_id=r.work_order_id, operator=current_user,
        remark=f"领用单 #{r.id} 出库" + (f"；{data.remark}" if data.remark else ""),
        source_type="REQUISITION", source_id=r.id,
    )
    part.reserved_quantity = normalize_qty(reserved - qty)

    for inst in insts:
        from app.models.part_instance import PartInstanceStatus
        if wo is not None and wo.device_id:
            inst.status = PartInstanceStatus.INSTALLED
            inst.device_id = wo.device_id
            inst.device_code = wo.device_code
            inst.installed_at = datetime.now()
        else:
            inst.status = PartInstanceStatus.ISSUED
            inst.removed_at = datetime.now()
        inst.work_order_id = r.work_order_id
        inst.outbound_movement_id = mv.id

    r.status = St.ISSUED
    r.movement_id = mv.id
    r.issued_at = datetime.now()
    if not r.approver_name:
        r.approver_name = current_user.real_name

    if wo is not None:
        used = list(wo.used_parts or [])
        used.append({
            "name": part.part_name, "code": part.part_code,
            "count": qty, "unit_price": billing_price,
        })
        wo.used_parts = used
        try:
            from app.services import sla as sla_service
            sla_service.recompute_cost(wo, db)
        except Exception as e:
            logger.warning(f"[Requisition] 工单成本重算失败: {e}")

    db.commit()
    db.refresh(r)
    cache_service.invalidate_pattern("stock_alerts:*")
    cache_service.delete(f"spare_part:{part.id}")
    logger.info(f"[Requisition] {rid} 出库 {part.part_code} x{qty:g}，库存 {stock:g} -> {part.stock_quantity}")

    try:
        from app.api.notifications import notify_user
        sn_txt = "、".join([i.sn for i in insts if i.sn]) if insts else ""
        wo_txt = f"，关联工单 {wo.work_order_no}" if wo is not None else ""
        notify_user(
            db, r.applicant_id, type="REQUISITION", title="备件已发料",
            content=f"你申请的 {part.part_code} {part.part_name} x{qty:g}{part.unit or ''} 已发料"
                    + (f"（SN：{sn_txt}）" if sn_txt else "") + wo_txt,
            work_order_id=r.work_order_id, level="P2", exclude_user_id=current_user.id,
        )
        if not _is_supervisor:
            # 申请人自助领料：通知主管/管理员留痕（谁什么时候领走的）
            from app.api.notifications import notify_roles
            notify_roles(
                db, ["ADMIN", "SUPERVISOR"], type="REQUISITION", title="备件已领料（申请人自助）",
                content=f"{current_user.real_name} 领用 {part.part_code} {part.part_name} "
                        f"x{qty:g}{part.unit or ''}"
                        + (f"（SN：{sn_txt}）" if sn_txt else "")
                        + (f"，关联工单 {wo.work_order_no}" if wo is not None else ""),
                work_order_id=r.work_order_id, level="P3", exclude_user_id=current_user.id,
            )
        if wo is not None and wo.technician_id and wo.technician_id != r.applicant_id:
            notify_user(
                db, wo.technician_id, type="REQUISITION", title="工单备件已发料",
                content=f"工单 {wo.work_order_no} 的备件 {part.part_code} {part.part_name} "
                        f"x{qty:g} 已发料" + (f"（SN：{sn_txt}）" if sn_txt else ""),
                work_order_id=r.work_order_id, level="P2", exclude_user_id=current_user.id,
            )
        db.commit()
    except Exception as e:
        logger.warning(f"[Requisition] 发料通知失败（忽略）: {e}")
    return _req_dict(r, part)


@router.post("/{rid}/cancel", summary="撤销申请（申请人自己撤销；已批准的会释放预占）")
def cancel_requisition(rid: int, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    r = _get(db, rid)
    if r.status not in (St.PENDING, St.APPROVED):
        raise HTTPException(status_code=400, detail="已出库/已驳回的申请不能撤销")
    is_owner = r.applicant_id == current_user.id
    is_supervisor = getattr(current_user.role, "value", current_user.role) in ("ADMIN", "SUPERVISOR")
    if not (is_owner or is_supervisor):
        raise HTTPException(status_code=403, detail="只能撤销自己的申请")

    part = lock_part(db, r.part_id)
    if r.status == St.APPROVED and part:
        part.reserved_quantity = normalize_qty(
            max(0.0, float(part.reserved_quantity or 0) - float(r.quantity or 0))
        )
    r.status = St.CANCELLED
    db.commit()
    db.refresh(r)
    cache_service.invalidate_pattern("stock_alerts:*")
    if part is not None:
        cache_service.delete(f"spare_part:{part.id}")
    try:
        from app.api.notifications import notify_roles
        notify_roles(
            db, ["ADMIN", "SUPERVISOR"], type="REQUISITION", title="领用申请已撤销",
            content=f"{current_user.real_name} 撤销了领用申请 #{r.id}（{r.part_code} "
                    f"{r.part_name} x{float(r.quantity or 0):g}），无需再处理",
            level="P3", exclude_user_id=current_user.id,
        )
        db.commit()
    except Exception as e:
        logger.warning(f"[Requisition] 撤销通知失败（忽略）: {e}")
    return _req_dict(r, part)

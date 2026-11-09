"""保养计划 API：计划 CRUD、到期提醒、执行保养、异常转工单"""
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_supervisor
from app.models.device import Device
from app.models.maintenance import MaintenancePlan, MaintenanceRecord
from app.models.user import User, UserRole
from app.models.work_order import WorkOrder, WorkOrderStatus

router = APIRouter(tags=["保养计划"], dependencies=[Depends(get_current_user)])


class PlanIn(BaseModel):
    plan_name: str = Field(..., max_length=200)
    device_code: Optional[str] = None
    items: Optional[str] = Field(None, description="保养项目，换行分隔")
    cycle_type: str = Field("DAYS")
    cycle_value: int = Field(30, ge=1, le=3650)
    responsible_id: Optional[int] = None
    next_due_at: Optional[datetime] = None
    remark: Optional[str] = None
    status: Optional[str] = "ACTIVE"


class PlanDoneIn(BaseModel):
    result: str = Field("OK", description="OK / ABNORMAL")
    cost: Optional[float] = None
    remark: Optional[str] = None
    create_work_order: bool = Field(False, description="异常时是否自动建处理工单")


def _plan_dict(p: MaintenancePlan, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now()
    overdue = bool(p.next_due_at and p.next_due_at < now)
    days_left = None
    if p.next_due_at:
        days_left = (p.next_due_at.date() - now.date()).days
    return {
        "id": p.id, "plan_name": p.plan_name,
        "device_id": p.device_id, "device_code": p.device_code,
        "items": p.items, "cycle_type": p.cycle_type, "cycle_value": p.cycle_value,
        "last_done_at": p.last_done_at.isoformat() if p.last_done_at else None,
        "next_due_at": p.next_due_at.isoformat() if p.next_due_at else None,
        "responsible_id": p.responsible_id, "responsible_name": p.responsible_name,
        "status": p.status or "ACTIVE", "remark": p.remark,
        "overdue": overdue, "days_left": days_left,
        "due_state": "OVERDUE" if overdue else ("DUE_SOON" if days_left is not None and days_left <= 3 else "OK"),
    }


@router.get("/plans", summary="保养计划列表")
def list_plans(
    status: Optional[str] = None,
    device_code: Optional[str] = None,
    only_due: bool = Query(False, description="只看到期/超期"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(MaintenancePlan)
    if status:
        q = q.filter(MaintenancePlan.status == status)
    if device_code:
        q = q.filter(MaintenancePlan.device_code == device_code)
    if only_due:
        q = q.filter(MaintenancePlan.next_due_at <= datetime.now() + timedelta(days=3))
    total = q.count()
    rows = q.order_by(MaintenancePlan.next_due_at.asc().nullslast()) \
            .offset((page - 1) * page_size).limit(page_size).all()
    now = datetime.now()
    return {"total": total, "page": page, "page_size": page_size,
            "items": [_plan_dict(p, now) for p in rows]}


@router.get("/stats", summary="保养概览：超期/临期/总数")
def maintenance_stats(db: Session = Depends(get_db)):
    now = datetime.now()
    total = db.query(MaintenancePlan).filter(MaintenancePlan.status == "ACTIVE").count()
    overdue = db.query(MaintenancePlan).filter(
        MaintenancePlan.status == "ACTIVE", MaintenancePlan.next_due_at < now).count()
    soon = db.query(MaintenancePlan).filter(
        MaintenancePlan.status == "ACTIVE",
        MaintenancePlan.next_due_at >= now,
        MaintenancePlan.next_due_at <= now + timedelta(days=3)).count()
    done_30d = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.done_at >= now - timedelta(days=30)).count()
    return {"total": total, "overdue": overdue, "due_soon": soon, "done_last_30d": done_30d}


@router.post("/plans", summary="新建保养计划（主管/管理员）")
def create_plan(data: PlanIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_supervisor)):
    dev = None
    if data.device_code:
        dev = db.query(Device).filter(Device.device_code == data.device_code).first()
    due = data.next_due_at or (datetime.now() + timedelta(days=data.cycle_value))
    plan = MaintenancePlan(
        plan_name=data.plan_name,
        device_id=dev.id if dev else None,
        device_code=data.device_code,
        items=data.items, cycle_type=data.cycle_type, cycle_value=data.cycle_value,
        next_due_at=due,
        responsible_id=data.responsible_id or current_user.id,
        responsible_name=(db.query(User).filter(User.id == (data.responsible_id or current_user.id)).first() or current_user).real_name,
        status=data.status or "ACTIVE", remark=data.remark,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    logger.info(f"[Maintenance] 新建保养计划 {plan.plan_name} 下次到期 {due:%Y-%m-%d}")
    return _plan_dict(plan)


@router.put("/plans/{plan_id}", summary="修改保养计划（主管/管理员）")
def update_plan(plan_id: int, data: PlanIn, db: Session = Depends(get_db),
                current_user: User = Depends(require_supervisor)):
    plan = db.query(MaintenancePlan).filter(MaintenancePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="保养计划不存在")
    plan.plan_name = data.plan_name
    plan.device_code = data.device_code
    plan.items = data.items
    plan.cycle_type, plan.cycle_value = data.cycle_type, data.cycle_value
    if data.next_due_at:
        plan.next_due_at = data.next_due_at
    if data.responsible_id:
        plan.responsible_id = data.responsible_id
        u = db.query(User).filter(User.id == data.responsible_id).first()
        plan.responsible_name = u.real_name if u else plan.responsible_name
    plan.status = data.status or plan.status
    plan.remark = data.remark
    db.commit()
    db.refresh(plan)
    return _plan_dict(plan)


@router.delete("/plans/{plan_id}", summary="删除保养计划（主管/管理员）")
def delete_plan(plan_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(require_supervisor)):
    plan = db.query(MaintenancePlan).filter(MaintenancePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="保养计划不存在")
    db.delete(plan)
    db.commit()
    return {"message": "已删除"}


@router.post("/plans/{plan_id}/done", summary="执行一次保养（自动顺延下次到期）")
def plan_done(plan_id: int, data: PlanDoneIn, db: Session = Depends(get_db),
              current_user: User = Depends(get_current_user)):
    plan = db.query(MaintenancePlan).filter(MaintenancePlan.id == plan_id).first()
    if not plan:
        raise HTTPException(status_code=404, detail="保养计划不存在")

    now = datetime.now()
    wo_id = None
    if data.result.upper() == "ABNORMAL" and data.create_work_order:
        wo = WorkOrder(
            work_order_no=f"PM-{now:%Y%m%d%H%M%S}",
            device_id=plan.device_id, device_code=plan.device_code,
            fault_description=f"保养异常：{plan.plan_name}\n{data.remark or ''}".strip(),
            fault_category="保养异常",
            order_type="MAINTENANCE",
            alert_level="P1",
            priority="HIGH",
            status=WorkOrderStatus.DRAFT,
            created_by=current_user.id, technician_id=current_user.id,
        )
        db.add(wo)
        db.flush()
        wo_id = wo.id

    rec = MaintenanceRecord(
        plan_id=plan.id, device_id=plan.device_id, device_code=plan.device_code,
        plan_name=plan.plan_name, done_at=now,
        done_by_id=current_user.id, done_by_name=current_user.real_name,
        result=data.result.upper(), cost=data.cost or 0,
        remark=data.remark, work_order_id=wo_id,
    )
    db.add(rec)

    plan.last_done_at = now
    plan.next_due_at = now + timedelta(days=plan.cycle_value or 30)
    db.commit()
    db.refresh(rec)
    logger.info(f"[Maintenance] 保养完成 {plan.plan_name}，下次 {plan.next_due_at:%Y-%m-%d}")
    return {
        "message": "保养已记录", "record_id": rec.id,
        "next_due_at": plan.next_due_at.isoformat(),
        "work_order_id": wo_id,
    }


@router.get("/records", summary="保养记录")
def list_records(
    plan_id: Optional[int] = None,
    device_code: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(MaintenanceRecord)
    if plan_id:
        q = q.filter(MaintenanceRecord.plan_id == plan_id)
    if device_code:
        q = q.filter(MaintenanceRecord.device_code == device_code)
    total = q.count()
    rows = q.order_by(MaintenanceRecord.done_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [{
        "id": r.id, "plan_id": r.plan_id, "plan_name": r.plan_name,
        "device_code": r.device_code, "done_at": r.done_at.isoformat() if r.done_at else None,
        "done_by_name": r.done_by_name, "result": r.result, "cost": r.cost,
        "remark": r.remark, "work_order_id": r.work_order_id,
    } for r in rows]}

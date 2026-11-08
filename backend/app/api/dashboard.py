"""Dashboard 聚合统计接口 — 一次请求返回所有统计数据"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date, func
from datetime import date, datetime, timedelta

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.models.knowledge import KnowledgeItem, KnowledgeStatus
from app.models.manual_code import ManualCodeEntry
from app.models.device import Device
from app.models.spare_part import SparePart
from app.models.user import User

router = APIRouter(dependencies=[Depends(get_current_user)])
def _wo_to_dict(w: WorkOrder) -> dict:
    return {c.name: getattr(w, c.name) for c in w.__table__.columns}


@router.get("/stats", summary="Dashboard 聚合统计")
def dashboard_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """一次查询返回数据驾驶舱所需的所有统计数据"""
    today = date.today()

    # 工单统计
    total_orders = db.query(func.count(WorkOrder.id)).scalar() or 0
    today_orders = db.query(func.count(WorkOrder.id)).filter(
        cast(WorkOrder.created_at, Date) == today
    ).scalar() or 0
    pending_review = db.query(func.count(WorkOrder.id)).filter(
        WorkOrder.status == WorkOrderStatus.DRAFT
    ).scalar() or 0

    # 知识统计
    total_knowledge = db.query(func.count(KnowledgeItem.id)).scalar() or 0
    published_knowledge = db.query(func.count(KnowledgeItem.id)).filter(
        KnowledgeItem.status == KnowledgeStatus.PUBLISHED
    ).scalar() or 0
    under_review_knowledge = db.query(func.count(KnowledgeItem.id)).filter(
        KnowledgeItem.status == KnowledgeStatus.UNDER_REVIEW
    ).scalar() or 0
    total_manual_codes = db.query(func.count(ManualCodeEntry.id)).scalar() or 0

    # 设备 & 备件统计
    total_devices = db.query(func.count(Device.id)).scalar() or 0
    total_spare_parts = db.query(func.count(SparePart.id)).scalar() or 0

    # 设备监控状态分布
    devices_all = db.query(Device.run_status, Device.fault_tags).all()
    device_monitor = {"online": 0, "offline": 0, "alarm": 0, "fault": 0, "unknown": 0,
                      "with_fault_tags": 0}
    for (s, ft) in devices_all:
        s_key = (s or "UNKNOWN").lower()
        if s_key not in device_monitor:
            s_key = "unknown"
        device_monitor[s_key] += 1
        if ft and len(ft) > 0:
            device_monitor["with_fault_tags"] += 1

    # 库存预警
    low_stock = db.query(SparePart).filter(
        SparePart.stock_quantity > 0,
        SparePart.stock_quantity <= SparePart.safety_stock
    ).all()
    out_of_stock = db.query(SparePart).filter(
        SparePart.stock_quantity <= 0
    ).all()
    stock_alert = len(low_stock) + len(out_of_stock)

    # 最近 6 条工单
    recent_orders = db.query(WorkOrder).order_by(
        WorkOrder.created_at.desc()
    ).limit(6).all()

    # ===== 管理指标：MTTR / 故障分布 / 备件消耗 / 维修员工作量 / 满意度 / 成本 =====
    from sqlalchemy import case
    from app.models.stock_movement import StockMovement

    finished = db.query(WorkOrder).filter(
        WorkOrder.resolved_at.isnot(None)
    ).all()
    mttr_hours = 0.0
    if finished:
        spans = []
        for w in finished:
            base = w.first_response_at or w.created_at
            if base and w.resolved_at:
                spans.append((w.resolved_at - base).total_seconds() / 3600.0)
        if spans:
            mttr_hours = round(sum(spans) / len(spans), 2)

    overdue_count = db.query(func.count(WorkOrder.id)).filter(
        WorkOrder.sla_status == "OVERDUE"
    ).scalar() or 0

    fault_top = db.query(
        func.coalesce(WorkOrder.fault_category, "未分类").label("k"),
        func.count(WorkOrder.id).label("n"),
    ).group_by("k").order_by(func.count(WorkOrder.id).desc()).limit(10).all()

    parts_top = db.query(
        StockMovement.part_name.label("k"),
        func.sum(StockMovement.quantity).label("n"),
        func.sum(StockMovement.amount).label("amt"),
    ).filter(StockMovement.movement_type == "OUT").group_by(StockMovement.part_name) \
     .order_by(func.sum(StockMovement.quantity).desc()).limit(10).all()

    tech_rows = db.query(
        WorkOrder.technician_id,
        func.count(WorkOrder.id).label("n"),
        func.coalesce(func.sum(WorkOrder.work_hours), 0).label("hours"),
    ).filter(WorkOrder.technician_id.isnot(None)).group_by(WorkOrder.technician_id) \
     .order_by(func.count(WorkOrder.id).desc()).limit(10).all()
    users_map = {u.id: u.real_name for u in db.query(User).all()}

    sat = db.query(func.avg(WorkOrder.satisfaction_score), func.count(WorkOrder.satisfaction_score)).first()
    cost_sum = db.query(func.coalesce(func.sum(WorkOrder.total_cost), 0)).scalar() or 0

    return {
        "total_orders": total_orders,
        "today_orders": today_orders,
        "pending_review": pending_review,
        "total_knowledge": total_knowledge,
        "total_manual_codes": total_manual_codes,
        "published_knowledge": published_knowledge,
        "under_review_knowledge": under_review_knowledge,
        "total_devices": total_devices,
        "total_spare_parts": total_spare_parts,
        "device_monitor": device_monitor,
        "stock_alert": stock_alert,
        "low_stock_items": [{c.name: getattr(s, c.name) for c in s.__table__.columns} for s in low_stock],
        "out_of_stock_items": [{c.name: getattr(s, c.name) for c in s.__table__.columns} for s in out_of_stock],
        "recent_orders": [_wo_to_dict(w) for w in recent_orders],
        # 新增管理指标
        "mttr_hours": mttr_hours,
        "overdue_count": overdue_count,
        "fault_top": [{"name": k, "count": n} for k, n in fault_top],
        "parts_top": [{"name": k, "quantity": round(float(n or 0), 2), "amount": round(float(a or 0), 2)}
                      for k, n, a in parts_top],
        "technician_workload": [{"name": users_map.get(tid, f"#{tid}"), "orders": n,
                                 "hours": round(float(h or 0), 1)} for tid, n, h in tech_rows],
        "satisfaction_avg": round(float(sat[0] or 0), 2) if sat and sat[0] else 0,
        "satisfaction_count": sat[1] if sat else 0,
        "total_cost": round(float(cost_sum), 2),
    }

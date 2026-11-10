from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import cast, Date, or_, and_
from typing import Optional, List, Dict, Any
from loguru import logger
from datetime import date, datetime, timedelta
import json

from app.core.database import get_db
from app.core.security import get_current_user
from app.services import sla as sla_service
from app.core import alert_level as AL
from app.core import status_group as SG
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.models.work_order_edit_log import WorkOrderEditLog
from app.models.work_order_collaborator import WorkOrderCollaborator
from app.models.device import Device
from app.models.spare_part import SparePart
from app.models.user import User, UserRole
from app.models.progress_log import WorkOrderProgressLog
from app.models.duty_schedule import DutySchedule
from app.schemas import (
    WorkOrderCreate, WorkOrderUpdate, WorkOrderResponse, PaginatedResponse,
    TicketAnalysisResponse, WorkOrderTransition, WorkOrderDispatchCreate,
    WorkOrderProgressLogResponse, WorkOrderFeedbackIn,
)
from app.agents.ticket_agent import ticket_agent
from app.agents.knowledge_extractor import knowledge_extractor
from app.agents.tools import extract_error_codes
from app.models.knowledge import KnowledgeItem, KnowledgeStatus

router = APIRouter(dependencies=[Depends(get_current_user)])


def _audit_value(v):
    """把字段值转成可写入 JSONB 的形式"""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    try:
        json.dumps(v)
        return v
    except Exception:
        return str(v)


def _set_collaborators(db: Session, work_order_id: int, collaborator_ids, primary_id=None) -> list:
    """覆盖式设置协作人：去重、排除主责、只允许启用中的维修员"""
    ids = []
    for i in collaborator_ids or []:
        try:
            i = int(i)
        except (TypeError, ValueError):
            continue
        if i and i != primary_id and i not in ids:
            ids.append(i)
    db.query(WorkOrderCollaborator).filter(
        WorkOrderCollaborator.work_order_id == work_order_id
    ).delete(synchronize_session=False)
    if ids:
        users = db.query(User).filter(
            User.id.in_(ids),
            User.is_active == True,
            User.role == UserRole.TECHNICIAN.value,
        ).all()
        for u in users:
            db.add(WorkOrderCollaborator(work_order_id=work_order_id, user_id=u.id))
    db.flush()
    return ids


def _collaborators_of(db: Session, work_order_id: int) -> list:
    rows = (db.query(WorkOrderCollaborator, User)
            .join(User, User.id == WorkOrderCollaborator.user_id)
            .filter(WorkOrderCollaborator.work_order_id == work_order_id)
            .order_by(WorkOrderCollaborator.id.asc()).all())
    return [{"id": u.id, "name": u.real_name} for _, u in rows]
def _wo_to_dict(w: WorkOrder) -> dict:
    return {c.name: getattr(w, c.name) for c in w.__table__.columns}


def _get_current_shift() -> str:
    """根据当前小时判断时段：MORNING / AFTERNOON / NIGHT"""
    hour = datetime.now().hour
    if 8 <= hour < 12:
        return "MORNING"
    elif 12 <= hour < 18:
        return "AFTERNOON"
    else:
        return "NIGHT"


@router.get("/", response_model=PaginatedResponse[WorkOrderResponse], summary="获取工单列表")
def list_work_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    status: Optional[str] = None,
    status_group: Optional[str] = Query(None, description="状态分组：DRAFT/SUBMITTED/PROCESSING/ARCHIVING/ARCHIVED/REJECTED"),
    mine: Optional[str] = Query(None, description="我的工单：assigned(派给我) / processing(我在处理) / created(我报修) / completed(我完成)"),
    keyword: Optional[str] = None,
    user_id: Optional[int] = Query(None, description="按用户名筛选：报修人 / 上报人 / 负责人"),
    device_type: Optional[str] = Query(None, description="设备类型筛选"),
    date_from: Optional[date] = Query(None, description="创建日期起始"),
    date_to: Optional[date] = Query(None, description="创建日期截止"),
    sla_status: Optional[str] = Query(None, description="SLA 状态筛：ON_TIME / AT_RISK / OVERDUE"),
    order_type: Optional[str] = Query(None, description="工单类型：REPAIR/MAINTENANCE/INSPECTION/IMPORT"),
    alert_level: Optional[str] = Query(None, description="告警级别：P0/P1/P2/P3"),
    overdue_only: bool = Query(False, description="只看超时工单"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(WorkOrder)
    if status_group:
        statuses = SG.statuses_of(status_group)
        if statuses:
            query = query.filter(WorkOrder.status.in_(statuses))
    if mine:
        me = current_user.id
        if mine == "pool":
            # 工单池：仅「待派工且尚未指派」的单，供维修员抢单
            query = query.filter(
                WorkOrder.status == WorkOrderStatus.SUBMITTED.value,
                WorkOrder.technician_id.is_(None),
            )
        elif mine == "all":
            # 我的：我创建的 或 派给我的（不区分状态）
            query = query.filter(or_(WorkOrder.created_by == me,
                                     WorkOrder.technician_id == me))
        elif mine == "assigned":
            # 派给我的（含待接受/处理中，排除已归档）
            query = query.filter(WorkOrder.technician_id == me)
            query = query.filter(WorkOrder.status.notin_([
                WorkOrderStatus.ARCHIVED.value, WorkOrderStatus.COMPLETED.value]))
        elif mine == "processing":
            query = query.filter(WorkOrder.technician_id == me)
            query = query.filter(WorkOrder.status.in_([
                WorkOrderStatus.ASSIGNED.value, WorkOrderStatus.ACCEPTED.value,
                WorkOrderStatus.ARRIVED.value, WorkOrderStatus.INSPECTING.value,
                WorkOrderStatus.IN_PROGRESS.value, WorkOrderStatus.ARCHIVING.value]))
        elif mine == "created":
            query = query.filter(WorkOrder.created_by == me)
        elif mine == "completed":
            query = query.filter(WorkOrder.technician_id == me)
            query = query.filter(WorkOrder.status.in_([
                WorkOrderStatus.COMPLETED.value, WorkOrderStatus.ARCHIVED.value]))
    elif status:
        query = query.filter(WorkOrder.status == status)
    if sla_status:
        query = query.filter(WorkOrder.sla_status == sla_status.upper())
    if order_type:
        query = query.filter(WorkOrder.order_type == order_type.upper())
    if alert_level:
        query = query.filter(WorkOrder.alert_level == AL.normalize(alert_level))
    if overdue_only:
        query = query.filter(WorkOrder.sla_status == "OVERDUE")
    if keyword:
        query = query.filter(
            WorkOrder.work_order_no.ilike(f"%{keyword}%") |
            WorkOrder.fault_description.ilike(f"%{keyword}%")
        )
    if user_id:
        # 按用户名筛选（管理员/主管）：该用户报修的、上报的、或当前负责的工单
        query = query.filter(or_(
            WorkOrder.created_by == user_id,
            WorkOrder.reporter_id == user_id,
            WorkOrder.technician_id == user_id,
            WorkOrder.assignee_id == user_id,
        ))
    if device_type:
        query = query.join(WorkOrder.device).filter(Device.device_type == device_type)
    if date_from:
        query = query.filter(cast(WorkOrder.created_at, Date) >= date_from)
    if date_to:
        query = query.filter(cast(WorkOrder.created_at, Date) <= date_to)
    total = query.count()
    items = query.order_by(WorkOrder.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    # 批量查询创建者/维修员信息（工号+姓名，用于前端权限判断和名字显示）
    user_ids = ({w.created_by for w in items if w.created_by}
                | {w.technician_id for w in items if w.technician_id}
                | {getattr(w, 'dispatcher_id', None) for w in items if getattr(w, 'dispatcher_id', None)})
    user_emp_map = {}
    user_name_map = {}
    if user_ids:
        users_q = db.query(User).filter(User.id.in_(user_ids)).all()
        user_emp_map = {u.id: u.employee_id for u in users_q}
        user_name_map = {u.id: u.real_name for u in users_q}
    # 是否为“别人转派给我”的单：批量取每人最近一条「改派：A → B」日志
    transfer_map = {}
    collab_map = {}
    item_ids = [w.id for w in items]
    if item_ids:
        collab_rows = (db.query(WorkOrderCollaborator, User)
                       .join(User, User.id == WorkOrderCollaborator.user_id)
                       .filter(WorkOrderCollaborator.work_order_id.in_(item_ids)).all())
        for c, u in collab_rows:
            collab_map.setdefault(c.work_order_id, []).append({"id": u.id, "name": u.real_name})
    assigned_ids = [w.id for w in items if w.status == WorkOrderStatus.ASSIGNED]
    if assigned_ids:
        logs = (db.query(WorkOrderProgressLog)
                .filter(WorkOrderProgressLog.work_order_id.in_(assigned_ids),
                        WorkOrderProgressLog.remark.like("改派：%"))
                .order_by(WorkOrderProgressLog.id.desc()).all())
        for lg in logs:
            if lg.work_order_id in transfer_map:
                continue
            remark = lg.remark or ""
            if "→" in remark:
                transfer_map[lg.work_order_id] = remark.split("：", 1)[1].split("→")[0].strip()
    result_items = []
    for w in items:
        d = _wo_to_dict(w)
        d['transfer_from_name'] = transfer_map.get(w.id)
        d['created_by_employee_id'] = user_emp_map.get(w.created_by) if w.created_by else None
        d['technician_name'] = user_name_map.get(w.technician_id) if w.technician_id else None
        d['device_type'] = w.device.device_type if w.device else None
        d['device_name'] = w.device.device_name if w.device else None
        # 告警级别：优先级映射，SLA 超时升 P0
        d['alert_level'] = getattr(w, 'alert_level', None) or AL.from_priority(getattr(w, 'priority', None))
        d['order_type'] = getattr(w, 'order_type', None) or 'REPAIR'
        d['dispatcher_name'] = user_name_map.get(getattr(w, 'dispatcher_id', None))
        d['dispatched_at'] = getattr(w, 'dispatched_at', None)
        d['collaborators'] = collab_map.get(w.id, [])
        d['status_group'] = SG.group_of(w.status)
        d['status_group_label'] = SG.label_of(w.status)
        result_items.append(d)
    return {"total": total, "items": result_items, "page": page, "page_size": page_size}


# ========== 进度看板 ==========

# display_status 中文映射
_DISPLAY_STATUS_MAP = {
    "SUBMITTED": "待派工",
    "ASSIGNED": "待接受",
    "ACCEPTED": "已接单",
    "ARRIVED": "已到达",
    "INSPECTING": "检查中",
    "IN_PROGRESS": "维修中",
    "COMPLETED": "已完成",
}


def _build_board_item(
    w: WorkOrder,
    tech_name_map: Dict[int, str],
    logs: List[WorkOrderProgressLog],
    now: datetime,
) -> dict:
    """构造看板工单项数据"""
    status_val = w.status.value if w.status else None

    # fault_description 截断100字
    fault_desc = w.fault_description or ""
    if len(fault_desc) > 100:
        fault_desc = fault_desc[:100]

    # 构造时间轴 [{status, timestamp, operator_name}]
    progress_timeline = [
        {
            "status": l.to_status.value if l.to_status else None,
            "timestamp": l.created_at,
            "operator_name": l.operator_name,
        }
        for l in logs
    ]

    # is_overtime: ASSIGNED状态且 created_at 距现在超过15分钟
    is_overtime = False
    if status_val == WorkOrderStatus.ASSIGNED.value and w.created_at:
        is_overtime = (now - w.created_at).total_seconds() > 15 * 60

    return {
        "id": w.id,
        "work_order_no": w.work_order_no,
        "device_code": w.device_code,
        "fault_description": fault_desc,
        "status": status_val,
        "display_status": _DISPLAY_STATUS_MAP.get(status_val, status_val),
        "technician_name": tech_name_map.get(w.technician_id) if w.technician_id else None,
        "created_at": w.created_at,
        "progress_timeline": progress_timeline,
        "is_overtime": is_overtime,
    }


@router.get("/progress-board", summary="进度看板（4列）")
def get_progress_board(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """一次性返回 4 列工单：待派工 / 待接受 / 处理中 / 已完成（近 7 天）

    口径说明：前两列与「处理中」列统计**全部未完结工单**（不限创建日期），
    与工单列表的分组筛选保持一致；「已完成」列展示近 7 天归档/完成的工单。
    """
    from datetime import timedelta

    today_start = datetime.combine(date.today(), datetime.min.time())
    recent_cutoff = datetime.now() - timedelta(days=7)

    open_statuses = [
        WorkOrderStatus.SUBMITTED.value,
        WorkOrderStatus.ASSIGNED.value,
        WorkOrderStatus.ACCEPTED.value,
        WorkOrderStatus.ARRIVED.value,
        WorkOrderStatus.INSPECTING.value,
        WorkOrderStatus.IN_PROGRESS.value,
        WorkOrderStatus.ARCHIVING.value,
    ]
    done_statuses = [
        WorkOrderStatus.COMPLETED.value,
        WorkOrderStatus.ARCHIVED.value,
    ]

    from sqlalchemy import or_, and_
    work_orders = (
        db.query(WorkOrder)
        .filter(or_(
            WorkOrder.status.in_(open_statuses),
            and_(WorkOrder.status.in_(done_statuses),
                 WorkOrder.updated_at >= recent_cutoff),
        ))
        .order_by(WorkOrder.created_at.asc())
        .all()
    )

    # 维修员姓名映射
    tech_ids = {w.technician_id for w in work_orders if w.technician_id}
    tech_name_map: Dict[int, str] = {}
    if tech_ids:
        techs = db.query(User).filter(User.id.in_(tech_ids)).all()
        tech_name_map = {t.id: t.real_name for t in techs}

    # 批量查询所有工单的进度日志（避免N+1查询）
    wo_ids = [w.id for w in work_orders]
    logs_by_wo: Dict[int, List[WorkOrderProgressLog]] = {}
    if wo_ids:
        all_logs = (
            db.query(WorkOrderProgressLog)
            .filter(WorkOrderProgressLog.work_order_id.in_(wo_ids))
            .order_by(WorkOrderProgressLog.work_order_id, WorkOrderProgressLog.created_at.asc())
            .all()
        )
        for log in all_logs:
            logs_by_wo.setdefault(log.work_order_id, []).append(log)

    # 状态分组
    in_progress_statuses = {
        WorkOrderStatus.ACCEPTED.value,
        WorkOrderStatus.ARRIVED.value,
        WorkOrderStatus.INSPECTING.value,
        WorkOrderStatus.IN_PROGRESS.value,
    }

    submitted_list: List[dict] = []
    assigned_list: List[dict] = []
    in_progress_list: List[dict] = []
    completed_list: List[dict] = []
    now = datetime.now()

    for w in work_orders:
        status_val = w.status.value if w.status else None
        item = _build_board_item(w, tech_name_map, logs_by_wo.get(w.id, []), now)

        if status_val == WorkOrderStatus.SUBMITTED.value:
            submitted_list.append(item)
        elif status_val == WorkOrderStatus.ASSIGNED.value:
            assigned_list.append(item)
        elif status_val in in_progress_statuses:
            in_progress_list.append(item)
        elif status_val in (WorkOrderStatus.ARCHIVING.value,
                            WorkOrderStatus.COMPLETED.value,
                            WorkOrderStatus.ARCHIVED.value):
            completed_list.append(item)

    return {
        "stats": {
            "submitted": len(submitted_list),
            "assigned": len(assigned_list),
            "in_progress": len(in_progress_list),
            "completed_today": len(completed_list),
        },
        "submitted": submitted_list,
        "assigned": assigned_list,
        "in_progress": in_progress_list,
        "completed": completed_list,
    }




@router.post("/{work_order_id}/start", summary="一键开始处理（受理→到场→检查→维修中）")
def start_processing(work_order_id: int, db: Session = Depends(get_db),
                     current_user: User = Depends(get_current_user)):
    """维修员接受任务后一键进入「维修中」，中间过程（接单/到场/检查）自动记录进度日志。

    对外只体现 6 个业务状态中的「处理中」，减少点击次数；原始状态仍逐条留痕。
    """
    from app.models.work_order import WorkOrderStatus

    wo = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")

    status_val = wo.status.value if wo.status else None
    path = []
    mode = (wo.service_mode or "").upper()
    remote_skip = mode in ("REMOTE", "RMA", "VENDOR")
    if status_val == WorkOrderStatus.SUBMITTED.value:
        path = [WorkOrderStatus.ASSIGNED.value]
    if status_val in (WorkOrderStatus.SUBMITTED.value, WorkOrderStatus.ASSIGNED.value):
        path += ([WorkOrderStatus.ACCEPTED.value, WorkOrderStatus.IN_PROGRESS.value] if remote_skip
                 else [WorkOrderStatus.ACCEPTED.value, WorkOrderStatus.ARRIVED.value,
                       WorkOrderStatus.INSPECTING.value, WorkOrderStatus.IN_PROGRESS.value])
    elif status_val == WorkOrderStatus.ACCEPTED.value:
        path = ([WorkOrderStatus.IN_PROGRESS.value] if remote_skip
                else [WorkOrderStatus.ARRIVED.value, WorkOrderStatus.INSPECTING.value, WorkOrderStatus.IN_PROGRESS.value])
    elif status_val == WorkOrderStatus.ARRIVED.value:
        path = [WorkOrderStatus.INSPECTING.value, WorkOrderStatus.IN_PROGRESS.value]
    elif status_val == WorkOrderStatus.INSPECTING.value:
        path = [WorkOrderStatus.IN_PROGRESS.value]
    elif status_val == WorkOrderStatus.IN_PROGRESS.value:
        return {"id": wo.id, "status": status_val, "status_group": SG.group_of(status_val),
                "message": "已在处理中"}
    else:
        raise HTTPException(status_code=400,
                            detail=f"当前状态 {SG.label_of(status_val)} 不能开始处理")

    prev = status_val
    for nxt in path:
        db.add(WorkOrderProgressLog(
            work_order_id=wo.id, from_status=WorkOrderStatus(prev), to_status=WorkOrderStatus(nxt),
            operator_id=current_user.id, operator_name=current_user.real_name,
            source="WEB", remark="一键开始处理",
        ))
        prev = nxt
    wo.status = WorkOrderStatus(prev)
    if not wo.technician_id:
        wo.technician_id = current_user.id
    db.commit()
    db.refresh(wo)
    _notify_wo(wo, "in_progress", actor=current_user.real_name)
    return {"id": wo.id, "status": prev, "status_group": SG.group_of(prev),
            "status_group_label": SG.label_of(prev)}


@router.get("/{work_order_id}/pdf", summary="导出单张工单 PDF")
def export_work_order_pdf(work_order_id: int, db: Session = Depends(get_db),
                          current_user: User = Depends(get_current_user)):
    """生成 A4 工单 PDF（含基本信息/故障处理/备件/费用/进度/签字栏），用于打印或存档"""
    from urllib.parse import quote
    from fastapi.responses import Response
    from app.services.work_order_pdf import build_work_order_pdf

    wo = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    tech = db.query(User).filter(User.id == wo.technician_id).first() if wo.technician_id else None
    creator = db.query(User).filter(User.id == wo.created_by).first() if wo.created_by else None
    disp_user = db.query(User).filter(User.id == wo.dispatcher_id).first() if wo.dispatcher_id else None
    pdf = build_work_order_pdf(
        wo,
        technician_name=tech.real_name if tech else None,
        creator_name=creator.real_name if creator else None,
        dispatcher_name=disp_user.real_name if disp_user else None,
        progress_logs=wo.progress_logs,
        device_name=wo.device.device_name if wo.device else None,
    )
    cn = f"工单-{wo.work_order_no}.pdf"
    ascii_name = f"work-order-{wo.work_order_no}.pdf"
    disp = "attachment; filename=\"" + ascii_name + "\"; filename*=UTF-8''" + quote(cn)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": disp})


@router.get("/{work_order_id}", response_model=WorkOrderResponse, summary="获取工单详情")
def get_work_order(work_order_id: int, db: Session = Depends(get_db)):
    work_order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")
    resp = WorkOrderResponse.model_validate(work_order)
    # 对外 6 状态分组（详情页与列表保持一致）
    resp.status_group = SG.group_of(work_order.status)
    resp.status_group_label = SG.label_of(work_order.status)
    # 设备信息（设备类型/名称）直接从关联设备返回，前端不依赖本地设备列表拼接
    if work_order.device:
        resp.device_type = work_order.device.device_type
        resp.device_name = work_order.device.device_name
    if work_order.created_by:
        creator = db.query(User).filter(User.id == work_order.created_by).first()
        resp.created_by_employee_id = creator.employee_id if creator else None
    # 维修员姓名（维修员=创建者，改名字后工单自动同步新名字）
    if work_order.technician_id:
        tech = db.query(User).filter(User.id == work_order.technician_id).first()
        resp.technician_name = tech.real_name if tech else None
    # 是否为别人转派给我的单（取最近一条「改派：A → B」进度日志）
    try:
        if work_order.status == WorkOrderStatus.ASSIGNED and work_order.progress_logs:
            for l in sorted(work_order.progress_logs, key=lambda x: x.id or 0, reverse=True):
                remark = (l.remark or "")
                if remark.startswith("改派：") and "→" in remark:
                    resp.transfer_from_name = remark.split("：", 1)[1].split("→")[0].strip()
                    break
    except Exception:
        resp.transfer_from_name = None
    resp.collaborators = _collaborators_of(db, work_order.id)
    return resp


@router.post("/", response_model=WorkOrderResponse, summary="创建草稿工单")
def create_work_order(data: WorkOrderCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """创建工单草稿，状态为 DRAFT，不触发 AI 分析"""
    # 自动生成工单编号: WO-YYYYMMDD-NNN
    if not data.work_order_no:
        today_str = date.today().strftime("%Y%m%d")
        prefix = f"WO-{today_str}-"
        latest = db.query(WorkOrder).filter(
            WorkOrder.work_order_no.like(f"{prefix}%")
        ).order_by(WorkOrder.work_order_no.desc()).first()
        if latest and latest.work_order_no:
            try:
                seq = int(latest.work_order_no.split("-")[-1]) + 1
            except ValueError:
                seq = 1
        else:
            seq = 1
        data.work_order_no = f"{prefix}{seq:03d}"
    existing = db.query(WorkOrder).filter(WorkOrder.work_order_no == data.work_order_no).first()
    if existing:
        raise HTTPException(status_code=400, detail="工单编号已存在")
    work_order = WorkOrder(**data.model_dump(exclude_unset=True))
    work_order.created_by = current_user.id
    # 只有维修员自己建单才自动归自己；管理员/主管建单不预占维修员，
    # 否则待派工工单"看起来已有人"，别人无法抢单。
    if current_user.role == UserRole.TECHNICIAN.value:
        work_order.technician_id = current_user.id
    else:
        work_order.technician_id = None
        work_order.assignee_id = None
    if work_order.status not in (WorkOrderStatus.DRAFT, None):
        work_order.status = WorkOrderStatus.DRAFT
    # 工单类型：显式传入优先，否则按来源推断（保养/点检自动建单已在各自模块设置）
    if not getattr(work_order, "order_type", None):
        work_order.order_type = "REPAIR"
    # 告警级别：按优先级推导
    work_order.alert_level = AL.from_priority(work_order.priority)
    # SLA：按优先级算出响应/修复截止时间
    try:
        resp_due, resv_due = sla_service.compute_due(work_order.priority or "MEDIUM")
        # 客户合同 SLA 优先于优先级默认值
        if work_order.customer_id:
            from app.models.customer import Customer
            cust = db.query(Customer).filter(Customer.id == work_order.customer_id).first()
            if cust:
                base = datetime.now()
                if cust.sla_response_hours is not None:
                    resp_due = base + timedelta(hours=cust.sla_response_hours)
                if cust.sla_resolve_hours is not None:
                    resv_due = base + timedelta(hours=cust.sla_resolve_hours)
        work_order.response_due_at = resp_due
        work_order.resolve_due_at = resv_due
        work_order.sla_status = "ON_TIME"
    except Exception as e:
        logger.warning(f"[WorkOrder] SLA 计算失败（忽略）: {e}")
    db.add(work_order)
    db.commit()
    db.refresh(work_order)
    logger.info(f"[WorkOrder] 创建草稿: {work_order.work_order_no}")
    _notify_wo(work_order, "created", actor=current_user.real_name)
    return _build_work_order_response(work_order, db)


@router.put("/{work_order_id}", response_model=WorkOrderResponse, summary="更新工单（逐步填写）")
def update_work_order(work_order_id: int, data: WorkOrderUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """维修过程中逐步保存表单内容。创建者、被指派的维修员或管理员可编辑。"""
    work_order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")
    if work_order.status == WorkOrderStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="已完成工单不可修改")
    if work_order.status == WorkOrderStatus.ARCHIVED and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="已归档工单仅管理员可修改")

    # 权限校验：创建者 / 被指派维修员（主管派工场景）/ 管理员可编辑
    is_assigned_tech = (
        (work_order.technician_id and work_order.technician_id == current_user.id)
        or (work_order.assignee_id and work_order.assignee_id == current_user.id)
    )
    if (
        work_order.created_by
        and current_user.id != work_order.created_by
        and not is_assigned_tech
        and current_user.role != UserRole.ADMIN.value
    ):
        raise HTTPException(status_code=403, detail="仅工单创建者、被指派维修员或管理员可编辑此工单")

    changes: Dict[str, Any] = {}
    for key, val in data.model_dump(exclude_unset=True).items():
        # 维修员和创建者不可通过更新修改（维修员锁定为创建者）
        if key in ("technician_id", "created_by"):
            continue
        before = getattr(work_order, key, None)
        if before != val:
            changes[key] = {"before": _audit_value(before), "after": _audit_value(val)}
        setattr(work_order, key, val)
    # 修复：保存草稿不再偷偷把 DRAFT 改成 IN_PROGRESS。
    # 状态推进统一走 /transition（提交报修 → 派工 → 接单 → 到场 → 检查 → 维修），
    # 否则编辑一次就跳过五个状态，状态机形同虚设。
    # 成本随工时/备件变化实时重算
    try:
        if data.work_hours is not None or data.used_parts is not None or work_order.work_hours:
            sla_service.recompute_cost(work_order, db)
    except Exception as e:
        logger.warning(f"[WorkOrder] 成本重算失败（忽略）: {e}")
    # 已归档工单：管理员修改留痕（审计）
    if work_order.status == WorkOrderStatus.ARCHIVED and changes:
        db.add(WorkOrderEditLog(
            work_order_id=work_order.id,
            editor_id=current_user.id,
            editor_name=current_user.real_name,
            status_at_edit="ARCHIVED",
            changes=changes,
        ))
        logger.info(f"[WorkOrder] 管理员 {current_user.real_name} 修改已归档工单 "
                    f"{work_order.work_order_no}，字段: {', '.join(changes)}")
    db.commit()
    db.refresh(work_order)
    return _build_work_order_response(work_order, db)


@router.get("/{work_order_id}/edit-logs", summary="工单修改记录（已归档工单管理员修改审计）")
def list_work_order_edit_logs(work_order_id: int, db: Session = Depends(get_db)):
    rows = (
        db.query(WorkOrderEditLog)
        .filter(WorkOrderEditLog.work_order_id == work_order_id)
        .order_by(WorkOrderEditLog.id.desc())
        .all()
    )
    return {
        "total": len(rows),
        "items": [
            {
                "id": r.id,
                "editor_name": r.editor_name,
                "status_at_edit": r.status_at_edit,
                "changes": r.changes or {},
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.post("/{work_order_id}/analyze", response_model=TicketAnalysisResponse, summary="AI 分析工单")
def analyze_work_order(work_order_id: int, db: Session = Depends(get_db)):
    """对工单执行 AI 标准化分析，返回分析结果但不改变状态"""
    work_order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")

    wo_data = {
        "fault_description": work_order.fault_description,
        "fault_code": work_order.fault_code,
        "fault_phenomenon": work_order.fault_phenomenon,
        "root_cause": work_order.root_cause,
        "solution_steps": work_order.solution_steps,
        "device_error_code": work_order.device_error_code,
        "device_type": getattr(work_order, "device_type", None),
        "log_text": work_order.log_text,
        "repair_result": work_order.repair_result,
        "work_hours": work_order.work_hours,
    }
    analysis = ticket_agent.analyze(wo_data)

    # 保存分析结果
    work_order.analysis_result = {
        "device_type": analysis.device_type,
        "fault_category": analysis.fault_category,
        "severity": analysis.severity,
        "completeness_score": analysis.completeness_score,
        "missing_fields": analysis.missing_fields,
        "validation_notes": analysis.validation_notes,
        "raw_reasoning": analysis.raw_reasoning,
        "suggested_actions": analysis.suggested_actions,
        "standardized_fields": {
            "fault_code": analysis.standardized_fault_code,
            "fault_phenomenon": analysis.standardized_fault_phenomenon,
            "root_cause": analysis.standardized_root_cause,
            "solution_steps": analysis.standardized_solution_steps,
        },
    }
    work_order.confidence = analysis.confidence
    db.commit()
    db.refresh(work_order)

    return TicketAnalysisResponse(
        work_order_id=work_order.id,
        standardized_fault_code=analysis.standardized_fault_code,
        standardized_fault_phenomenon=analysis.standardized_fault_phenomenon,
        standardized_root_cause=analysis.standardized_root_cause,
        standardized_solution_steps=analysis.standardized_solution_steps,
        device_type=analysis.device_type,
        fault_category=analysis.fault_category,
        tags=analysis.tags,
        severity=analysis.severity,
        completeness_score=analysis.completeness_score,
        missing_fields=analysis.missing_fields,
        validation_notes=analysis.validation_notes,
        confidence=analysis.confidence,
        raw_reasoning=analysis.raw_reasoning,
        suggested_actions=analysis.suggested_actions,
    )


@router.post("/{work_order_id}/complete", summary="提交完成工单（AI 分析+去重+收录知识）")
def complete_work_order(work_order_id: int, db: Session = Depends(get_db)):
    """
    维修人员确认全部填写完成并提交：
    1. AI 标准化分析（补全缺失的标准化字段）
    2. 自动提取结构化知识 + 去重检测
    3. 非重复 → 发布到知识库 → 同步 Milvus
    4. 工单状态改为 COMPLETED
    返回 knowledge_synced 标识知识是否被收录
    """
    work_order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")
    if work_order.status == WorkOrderStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="工单已完成")
    # 修复：只有维修中的工单才能提交完成，避免 DRAFT/SUBMITTED 直接跳到 COMPLETED 跳过整个状态机
    if work_order.status != WorkOrderStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=400,
            detail=f"仅「维修中」的工单可提交完成，当前状态：{work_order.status.value if hasattr(work_order.status, 'value') else work_order.status}",
        )

    # 1. AI 标准化分析
    wo_data = {
        "fault_description": work_order.fault_description,
        "fault_code": work_order.fault_code,
        "fault_phenomenon": work_order.fault_phenomenon,
        "root_cause": work_order.root_cause,
        "solution_steps": work_order.solution_steps,
        "device_error_code": work_order.device_error_code,
        "device_type": getattr(work_order, "device_type", None),
        "log_text": work_order.log_text,
        "repair_result": work_order.repair_result,
        "work_hours": work_order.work_hours,
    }
    try:
        analysis = ticket_agent.analyze(wo_data)
        work_order.confidence = analysis.confidence
        work_order.analysis_result = {
            "device_type": analysis.device_type,
            "fault_category": analysis.fault_category,
            "severity": analysis.severity,
            "completeness_score": analysis.completeness_score,
            "missing_fields": analysis.missing_fields,
            "validation_notes": analysis.validation_notes,
            "raw_reasoning": analysis.raw_reasoning,
            "suggested_actions": analysis.suggested_actions,
            "standardized_fields": {
                "fault_code": analysis.standardized_fault_code,
                "fault_phenomenon": analysis.standardized_fault_phenomenon,
                "root_cause": analysis.standardized_root_cause,
                "solution_steps": analysis.standardized_solution_steps,
            },
        }
        # 补全标准化字段
        if analysis.standardized_fault_code and not work_order.fault_code:
            work_order.fault_code = analysis.standardized_fault_code
        if analysis.standardized_fault_phenomenon and not work_order.fault_phenomenon:
            work_order.fault_phenomenon = analysis.standardized_fault_phenomenon
        if analysis.standardized_root_cause and not work_order.root_cause:
            work_order.root_cause = analysis.standardized_root_cause
        if analysis.standardized_solution_steps and not work_order.solution_steps:
            work_order.solution_steps = analysis.standardized_solution_steps
        if analysis.tags:
            work_order.tags = analysis.tags
    except Exception as e:
        logger.warning(f"[WorkOrder] 提交时 AI 分析失败: {e}")

    # 2. 自动提取知识并发布（含去重检测）
    knowledge_synced = False
    try:
        knowledge_synced = _auto_publish_knowledge(work_order, db)
    except Exception as e:
        logger.warning(f"[WorkOrder] 知识收录失败: {e}")

    # 2.5 扣减备件库存
    deduction_details = _deduct_spare_parts(work_order, db)

    # 2.6 收录故障码到映射表（一一对应，不可修改）
    _ensure_fault_code_mappings(work_order, db)

    # 3. 标记完成
    work_order.status = WorkOrderStatus.COMPLETED
    work_order.resolved_at = work_order.resolved_at or datetime.now()
    try:
        sla_service.recompute_cost(work_order, db)
        sla_service.mark_overdue(work_order)
        work_order.alert_level = "P0" if work_order.sla_status == "OVERDUE" else AL.from_priority(work_order.priority)  # 完成时刷新 alert_level
    except Exception as e:
        logger.warning(f"[WorkOrder] 完成时刷新 SLA/成本失败（忽略）: {e}")
    db.commit()
    db.refresh(work_order)
    logger.info(f"[WorkOrder] 工单 {work_order.work_order_no} 已提交完成，knowledge_synced={knowledge_synced}")
    return {
        "id": work_order.id,
        "work_order_no": work_order.work_order_no,
        "status": "COMPLETED",
        "sla_status": work_order.sla_status,
        "labor_cost": work_order.labor_cost,
        "parts_cost": work_order.parts_cost,
        "total_cost": work_order.total_cost,
        "knowledge_synced": knowledge_synced,
        "message": "知识已收录到知识库" if knowledge_synced else "提交成功（检测到相似知识，未重复收录）",
        "inventory_deducted": deduction_details,
    }


@router.delete("/{work_order_id}", summary="删除工单")
def delete_work_order(work_order_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    work_order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")
    # 权限校验：仅创建者或管理员可删除
    if work_order.created_by and current_user.id != work_order.created_by and current_user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=403, detail="仅工单创建者或管理员可删除此工单")
    # 删除工单前清理关联站内通知，避免通知点进去指向已删除工单
    try:
        from app.models.notification import Notification
        db.query(Notification).filter(
            Notification.work_order_id == work_order.id
        ).delete(synchronize_session=False)
    except Exception as e:
        logger.warning(f"[WorkOrder] 清理关联通知失败（忽略）: {e}")
    db.delete(work_order)
    db.commit()
    return {"message": "工单已删除"}


# ========== 内部函数 ==========

def _join_fault_codes(*parts) -> str:
    """合并多来源的故障码/设备错误码（去重，逗号分隔）——系统故障码 + 设备错误码"""
    seen, out = set(), []
    for p in parts:
        if not p:
            continue
        for c in str(p).replace("，", ",").split(","):
            c = c.strip()
            if c and c not in seen:
                seen.add(c)
                out.append(c)
    return ", ".join(out)


def _auto_publish_knowledge(wo: WorkOrder, db: Session) -> bool:
    """
    从工单提取知识 → 去重 → 直接发布到知识库
    返回 True 表示已收录，False 表示跳过（重复或提取失败）
    """
    # 同一工单不重复提取
    existing = db.query(KnowledgeItem).filter(
        KnowledgeItem.source_type == "WORK_ORDER",
        KnowledgeItem.source_id == wo.id,
    ).first()
    if existing:
        logger.info(f"[WorkOrder] 工单 {wo.work_order_no} 已提取过知识 #{existing.id}，跳过")
        return False

    analysis = wo.analysis_result if isinstance(wo.analysis_result, dict) else {}
    wo_data = {
        "fault_description": wo.fault_description,
        "fault_code": wo.fault_code,
        "device_error_code": wo.device_error_code,   # 设备运行日志错误码（SV0436 等），提取器可识别
        "log_text": wo.log_text,                     # 日志原文：仅用于抠码/信号词，不整段进正文
        "fault_phenomenon": wo.fault_phenomenon,
        "root_cause": wo.root_cause,
        "solution_steps": wo.solution_steps,
        "device_type": analysis.get("device_type", ""),
        "tags": wo.tags or [],
    }

    extracted = knowledge_extractor.extract(wo_data)
    if not extracted.title:
        logger.warning(f"[WorkOrder] 工单 {wo.work_order_no} 知识提取返回空内容")
        return False

    # 去重检测
    from app.api.knowledge import _check_duplicate
    dedup = _check_duplicate(extracted, db)

    if dedup.has_duplicate:
        true_dups = [m for m in dedup.matched_items if m.get("is_true_duplicate")]
        logger.info(
            f"[WorkOrder] 检测到真重复知识 (相似度={dedup.similarity_score:.2f}): "
            f"{[m.get('title','') for m in true_dups[:2]]}，跳过自动收录"
        )
        return False

    # 创建并发布知识
    # 知识条目的故障码 = 系统故障码 + 设备错误码合并（让检索"报SV0436"能命中该工单案例）
    knowledge = KnowledgeItem(
        title=extracted.title,
        content=extracted.content,
        device_type=extracted.device_type,
        fault_code=_join_fault_codes(extracted.fault_code, wo.device_error_code),
        fault_tags=extracted.fault_tags,
        source_type="WORK_ORDER",
        source_id=wo.id,
        status=KnowledgeStatus.PUBLISHED,
        extraction_meta={
            "work_order_no": wo.work_order_no,
            "dedup_score": dedup.similarity_score,
            "keywords": extracted.keywords,
            "device_error_code": wo.device_error_code,
            "log_error_codes": extract_error_codes(wo.log_text or "") or [],
        },
    )
    db.add(knowledge)
    db.commit()
    db.refresh(knowledge)

    # 同步到 Milvus
    try:
        from app.api.knowledge import _sync_to_milvus
        _sync_to_milvus(knowledge, db)
    except Exception as e:
        logger.warning(f"[WorkOrder] 知识向量同步失败: {e}")

    logger.info(f"[WorkOrder] 从工单 {wo.work_order_no} 自动收录知识 #{knowledge.id}: {knowledge.title[:40]}...")
    return True


def _deduct_spare_parts(wo: WorkOrder, db: Session) -> List[dict]:
    """工单完成时的备件核对（不再直接扣库存）

    库存只能由「出库 / 领用 / 装机」动作扣减并留流水。工单完成时如果再去改库存，
    同一批料会被扣两次、而且没有凭证。这里只核对 used_parts 与当前库存，提示缺口。
    """
    used_parts = wo.used_parts
    if not used_parts or not isinstance(used_parts, list) or len(used_parts) == 0:
        return []

    details = []
    for part in used_parts:
        code = str(part.get("code") or "").strip()
        if not code:
            continue
        qty = part.get("count", part.get("qty", 0)) or 0

        spare = db.query(SparePart).filter(SparePart.part_code == code).first()
        if not spare:
            logger.warning(f"[WorkOrder] used_parts 里的备件 {code} 不在备件台账中（跳过核对）")
            details.append({
                "part_code": code,
                "part_name": part.get("name", ""),
                "requested": qty,
                "status": "not_in_ledger",
            })
            continue

        details.append({
            "part_code": code,
            "part_name": spare.part_name,
            "requested": qty,
            "remaining_stock": float(spare.stock_quantity or 0),
            "status": "recorded",
            "hint": "库存已在领用/出库时扣减；未走出库的请补一张出库单",
        })
    return details


def _ensure_fault_code_mappings(wo: WorkOrder, db: Session):
    """工单完成时，收录故障码到映射表（一一对应，不可修改）"""
    from app.api.fault_codes import ensure_fault_code_mapping

    codes = wo.fault_code
    if not codes:
        return

    # 解析逗号分隔的故障码
    code_list = [c.strip() for c in codes.split(",") if c.strip()]
    description = f"{wo.fault_description or ''} {wo.fault_phenomenon or ''}".strip()
    if not description:
        description = wo.fault_description or ""

    # 获取设备类型
    device_type = ""
    if wo.analysis_result and isinstance(wo.analysis_result, dict):
        device_type = wo.analysis_result.get("device_type", "")

    for code in code_list:
        try:
            ensure_fault_code_mapping(
                db, fault_code=code, fault_description=description,
                device_type=device_type, source="system",
            )
        except Exception as e:
            logger.warning(f"[WorkOrder] 故障码收录失败 {code}: {e}")


# ========== Phase1 工单流转与派工 ==========

VALID_TRANSITIONS: Dict[str, List[str]] = {
    WorkOrderStatus.DRAFT.value: [WorkOrderStatus.SUBMITTED.value, WorkOrderStatus.ASSIGNED.value],
    WorkOrderStatus.SUBMITTED.value: [WorkOrderStatus.ASSIGNED.value, WorkOrderStatus.REJECTED.value],
    WorkOrderStatus.ASSIGNED.value: [WorkOrderStatus.ACCEPTED.value, WorkOrderStatus.SUBMITTED.value, WorkOrderStatus.REJECTED.value],
    WorkOrderStatus.ACCEPTED.value: [WorkOrderStatus.ARRIVED.value, WorkOrderStatus.REJECTED.value],
    WorkOrderStatus.ARRIVED.value: [WorkOrderStatus.INSPECTING.value, WorkOrderStatus.REJECTED.value],
    WorkOrderStatus.INSPECTING.value: [WorkOrderStatus.IN_PROGRESS.value, WorkOrderStatus.REJECTED.value],
    WorkOrderStatus.IN_PROGRESS.value: [WorkOrderStatus.ARCHIVING.value, WorkOrderStatus.REJECTED.value],
    WorkOrderStatus.ARCHIVING.value: [WorkOrderStatus.ARCHIVED.value],
    WorkOrderStatus.COMPLETED.value: [],
    WorkOrderStatus.REJECTED.value: [],
    WorkOrderStatus.STANDARDIZED.value: [],
    WorkOrderStatus.CLASSIFIED.value: [],
    WorkOrderStatus.APPROVED.value: [],
    WorkOrderStatus.ARCHIVED.value: [],
}

WORKLOAD_INCREASE_STATUSES = {WorkOrderStatus.ASSIGNED.value}
WORKLOAD_DECREASE_STATUSES = {WorkOrderStatus.COMPLETED.value, WorkOrderStatus.REJECTED.value}


def _is_allowed_transition(from_status: str, to_status: str) -> bool:
    allowed = VALID_TRANSITIONS.get(from_status, [])
    return to_status in allowed


def _add_progress_log(
    db: Session,
    work_order_id: int,
    from_status: Optional[str],
    to_status: str,
    operator_id: Optional[int],
    operator_name: Optional[str],
    source: str,
    remark: Optional[str] = None,
    location: Optional[str] = None,
    attachments: Any = None,
) -> WorkOrderProgressLog:
    log = WorkOrderProgressLog(
        work_order_id=work_order_id,
        from_status=from_status,
        to_status=to_status,
        operator_id=operator_id,
        operator_name=operator_name,
        source=source,
        remark=remark,
        location=location,
        attachments=attachments,
    )
    db.add(log)
    db.flush()
    return log


def _notify_returned_to_pool(wo: WorkOrder, actor, reason: str = "") -> None:
    """拒收回池：通知原派工人 + 主管/管理员（独立会话）"""
    try:
        from app.core.database import SessionLocal
        from app.api.notifications import create_notification
        if not wo:
            return
        db = SessionLocal()
        try:
            users = db.query(User).filter(
                User.is_active == True,
                User.role.in_([UserRole.ADMIN.value, UserRole.SUPERVISOR.value]),
            ).all()
            targets = {u.id: u for u in users}
            if wo.dispatcher_id:
                dispatcher = db.query(User).filter(User.id == wo.dispatcher_id).first()
                if dispatcher:
                    targets[dispatcher.id] = dispatcher
            for u in targets.values():
                create_notification(
                    db, user_id=u.id, type="WORK_ORDER",
                    title="工单被拒收，已回到待派工池",
                    content=f"{getattr(actor, 'real_name', '维修员')} 拒收了工单 "
                            f"{wo.work_order_no}，原因：{reason or '-'}，请重新派工。",
                    work_order_id=wo.id,
                    level=AL.from_priority(getattr(wo, "priority", None)),
                )
            if targets:
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[WorkOrder] 拒收通知写入失败（忽略）: {e}")


def _notify_inapp(wo: WorkOrder, event: str, actor: str = "", extra: str = "") -> None:
    """站内通知（独立会话；失败不影响业务）"""
    try:
        from app.core.database import SessionLocal
        from app.api.notifications import create_notification
        if event not in ("submitted", "assigned", "rejected", "archived"):
            return
        level = AL.from_priority(getattr(wo, "priority", None))
        wo_no = wo.work_order_no
        fault = (wo.fault_description or "")[:60]
        device = wo.device_code or (f"设备#{wo.device_id}" if wo.device_id else "未指定设备")
        title_map = {
            "submitted": "新报修工单待派工",
            "assigned": "工单派工通知",
            "rejected": "工单被退回",
            "archived": "工单已归档",
        }
        content_map = {
            "submitted": f"工单 {wo_no}（{device}）已提交报修，等待派工。故障：{fault}",
            "assigned": f"工单 {wo_no}（{device}）已派发给你。故障：{fault}"
                        + (f"（{extra}）" if extra else ""),
            "rejected": f"工单 {wo_no}（{device}）被退回。{('原因：' + extra) if extra else ''}",
            "archived": f"工单 {wo_no}（{device}）已归档完成。{extra}",
        }
        db = SessionLocal()
        try:
            if event == "submitted":
                users = db.query(User).filter(
                    User.is_active == True,
                    User.role.in_([UserRole.ADMIN.value, UserRole.SUPERVISOR.value]),
                ).all()
            elif event == "assigned":
                tech = db.query(User).filter(User.id == wo.technician_id).first() if wo.technician_id else None
                users = [tech] if tech else []
                # 协作人另发一条「协作通知」
                collab_users = (db.query(User)
                                .join(WorkOrderCollaborator, WorkOrderCollaborator.user_id == User.id)
                                .filter(WorkOrderCollaborator.work_order_id == wo.id).all())
                for cu in collab_users:
                    if tech and cu.id == tech.id:
                        continue
                    create_notification(
                        db, user_id=cu.id, type="WORK_ORDER", title="工单协作通知",
                        content=f"你被加入工单 {wo_no}（{device}）协作，主责："
                                f"{(tech.real_name if tech else '-')}。故障：{fault}"
                                + (f"（{extra}）" if extra else ""),
                        work_order_id=wo.id, level=level,
                    )
            else:
                creator = db.query(User).filter(User.id == wo.created_by).first() if wo.created_by else None
                users = [creator] if creator else []
            for u in users:
                create_notification(
                    db, user_id=u.id, type="WORK_ORDER", title=title_map[event],
                    content=content_map[event], work_order_id=wo.id, level=level,
                )
            if users:
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"[WorkOrder] 站内通知写入失败（忽略）: {e}")


def _notify_wo(wo: WorkOrder, event: str, actor: str = "", extra: str = "") -> None:
    """钉钉自定义群机器人推送（未配置 webhook 直接跳过；内部异步发送，不阻塞接口）"""
    _notify_inapp(wo, event, actor=actor, extra=extra)
    try:
        from app.core.dingtalk_group import group_robot
        if not group_robot.enabled:
            return
        tech_name = ""
        try:
            tech_name = wo.technician.real_name if wo.technician else ""
        except Exception:
            tech_name = ""
        group_robot.work_order_event(event, {
            "id": wo.id,
            "work_order_no": wo.work_order_no,
            "device_code": wo.device_code,
            "fault_description": wo.fault_description,
            "priority": wo.priority,
            "location": wo.location,
            "status": wo.status.value if hasattr(wo.status, "value") else wo.status,
            "technician_name": tech_name,
            "reporter_name": actor,
        }, extra=extra)
    except Exception as e:  # 推送失败绝不影响业务
        logger.warning(f"[WorkOrder] 群机器人推送失败（忽略）: {e}")


def _update_workload(db: Session, technician_id: Optional[int], delta: int):
    if not technician_id or delta == 0:
        return
    tech = db.query(User).filter(User.id == technician_id).first()
    if tech:
        new_count = max(0, (tech.current_workload_count or 0) + delta)
        tech.current_workload_count = new_count
        db.flush()


@router.post("/{work_order_id}/transition", response_model=WorkOrderResponse, summary="工单状态流转")
def transition_work_order(
    work_order_id: int,
    data: WorkOrderTransition,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        return _do_transition(work_order_id, data, db, current_user)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        logger.error(f"[Transition] 工单 #{work_order_id} 流转异常: {e}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"工单流转内部错误: {e}")


def _do_transition(work_order_id: int, data: WorkOrderTransition, db: Session, current_user: User):
    try:
        to_status_val = data.to_status.upper()
        to_status_enum = WorkOrderStatus(to_status_val)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"无效的目标状态: {data.to_status}")

    work_order = (
        db.query(WorkOrder)
        .filter(WorkOrder.id == work_order_id)
        .first()
    )
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")

    from_status_val = work_order.status.value if work_order.status else None

    if from_status_val == to_status_val:
        # 状态不变，仅更换负责人：已派单 / 已接单 / 已到场 / 检查中
        reassignable = {
            WorkOrderStatus.ASSIGNED.value,
            WorkOrderStatus.ACCEPTED.value,
            WorkOrderStatus.ARRIVED.value,
            WorkOrderStatus.INSPECTING.value,
        }
        if to_status_val not in reassignable:
            raise HTTPException(status_code=400, detail="当前状态不支持转派/改派")
        if not data.technician_id:
            raise HTTPException(status_code=400, detail="转派必须指定新维修员")
        if data.technician_id == work_order.technician_id:
            raise HTTPException(status_code=400, detail="新负责人与当前负责人相同，无需转派")

        is_supervisor_role = current_user.role in (UserRole.SUPERVISOR.value, UserRole.ADMIN.value)
        is_owner = work_order.technician_id == current_user.id
        if not is_supervisor_role:
            # 维修员只能在「已派单」阶段转派自己名下的工单
            if to_status_val != WorkOrderStatus.ASSIGNED.value or not is_owner:
                raise HTTPException(
                    status_code=403,
                    detail="只有主管/管理员可改派；维修员仅能在已派单阶段转派自己名下的工单")
        # 接单之后改派可能已产生现场工作，必须写原因
        if to_status_val in (WorkOrderStatus.ACCEPTED.value,
                             WorkOrderStatus.ARRIVED.value,
                             WorkOrderStatus.INSPECTING.value) \
                and not (data.remark or "").strip():
            raise HTTPException(status_code=400, detail="接单后改派必须填写改派原因")

        tech = db.query(User).filter(
            User.id == data.technician_id, User.is_active == True).first()
        if not tech:
            raise HTTPException(status_code=400, detail="指定的维修员不存在或已停用")
        if tech.role != UserRole.TECHNICIAN.value:
            raise HTTPException(status_code=400, detail="只能转派给维修员")

        old_tech = db.query(User).filter(User.id == work_order.technician_id).first()
        old_name = old_tech.real_name if old_tech else "-"
        old_id = work_order.technician_id

        work_order.technician_id = tech.id
        work_order.assignee_id = tech.id
        work_order.dispatcher_id = current_user.id
        work_order.dispatched_at = datetime.now()
        if data.collaborator_ids is not None:
            _set_collaborators(db, work_order.id, data.collaborator_ids, primary_id=tech.id)
        _add_progress_log(
            db=db, work_order_id=work_order.id,
            from_status=work_order.status, to_status=work_order.status,
            operator_id=current_user.id, operator_name=current_user.real_name,
            source=data.source or "WEB",
            remark=f"改派：{old_name} → {tech.real_name}" + (f"（{data.remark}）" if data.remark else ""),
        )
        # 工作量：原维修员减一，新维修员加一
        if old_id:
            _update_workload(db, old_id, -1)
        _update_workload(db, tech.id, +1)
        # 通知原负责人：工单已转出
        try:
            from app.api.notifications import create_notification
            create_notification(
                db, user_id=old_id, type="WORK_ORDER", title="工单已转出",
                content=f"工单 {work_order.work_order_no} 已由你转给 {tech.real_name}"
                        + (f"，原因：{data.remark}" if data.remark else ""),
                work_order_id=work_order.id,
                level=AL.from_priority(getattr(work_order, "priority", None)),
            )
        except Exception as e:
            logger.warning(f"[WorkOrder] 转出通知写入失败（忽略）: {e}")
        db.commit()
        db.refresh(work_order)
        logger.info(f"[WorkOrder] 改派 #{work_order.id}: {old_name} -> {tech.real_name} "
                    f"（状态 {from_status_val}，操作人 {current_user.real_name}）")
        try:
            _notify_wo(work_order, "assigned", current_user.real_name,
                       extra=f"改派：{old_name} → {tech.real_name}")
        except Exception as e:
            logger.warning(f"[WorkOrder] 改派通知失败（忽略）: {e}")
        return _build_work_order_response(work_order, db)

    # 远程/返厂/第三方现场：接单后可直接进入处理中，不强制「到场/检查」
    mode = (work_order.service_mode or "").upper()
    remote_skip = mode in ("REMOTE", "RMA", "VENDOR")
    allowed = _is_allowed_transition(from_status_val, to_status_val)
    if (not allowed and remote_skip
            and from_status_val == WorkOrderStatus.ACCEPTED.value
            and to_status_val == WorkOrderStatus.IN_PROGRESS.value):
        allowed = True
    if not allowed:
        raise HTTPException(
            status_code=400,
            detail=f"非法状态流转: {from_status_val} → {to_status_val}，允许的目标状态: {VALID_TRANSITIONS.get(from_status_val, [])}"
        )
    if work_order.is_on_hold:
        raise HTTPException(status_code=400, detail="工单处于挂起状态，请先恢复后再流转")

    is_admin = current_user.role == UserRole.ADMIN.value
    is_supervisor = current_user.role == UserRole.SUPERVISOR.value
    is_technician = current_user.role == UserRole.TECHNICIAN.value
    is_assigned_tech = work_order.technician_id == current_user.id

    if to_status_val == WorkOrderStatus.ACCEPTED.value:
        if not (is_assigned_tech or is_admin):
            raise HTTPException(status_code=403, detail="仅被指派的维修员或管理员可接单")

    elif to_status_val == WorkOrderStatus.SUBMITTED.value:
        # 仅「已派单 → 待派工」是拒收回池；草稿提交报修不受此限制
        if from_status_val == WorkOrderStatus.ASSIGNED.value:
            if not (is_assigned_tech or is_admin):
                raise HTTPException(status_code=403, detail="仅当前负责人或管理员可拒收该工单")
            if not (data.remark or "").strip():
                raise HTTPException(status_code=400, detail="拒收必须填写原因")

    elif to_status_val in (WorkOrderStatus.ARRIVED.value, WorkOrderStatus.INSPECTING.value, WorkOrderStatus.IN_PROGRESS.value):
        if not (is_assigned_tech or is_admin):
            raise HTTPException(status_code=403, detail="仅维修员或管理员可推进到此状态")

    elif to_status_val == WorkOrderStatus.ARCHIVING.value:
        # 完成维修 → 待归档：仅被指派维修员或管理员可操作
        if not (is_assigned_tech or is_admin):
            raise HTTPException(status_code=403, detail="仅维修员或管理员可将工单标记为待归档")

    elif to_status_val == WorkOrderStatus.ARCHIVED.value:
        raise HTTPException(status_code=400, detail="归档完成请使用工单归档接口，需 AI 校验完成度达标")

    elif to_status_val == WorkOrderStatus.COMPLETED.value:
        pass

    elif to_status_val == WorkOrderStatus.REJECTED.value:
        if not (is_assigned_tech or is_admin or is_supervisor):
            raise HTTPException(status_code=403, detail="仅维修员、主管或管理员可退回")

    elif to_status_val == WorkOrderStatus.ASSIGNED.value:
        if is_supervisor or is_admin:
            # 派工 / 改派：必须指定维修员（否则状态变了但没人负责）
            if data.technician_id:
                tech = db.query(User).filter(User.id == data.technician_id).first()
                if not tech or not tech.is_active:
                    raise HTTPException(status_code=400, detail="指定的维修员不存在或已停用")
                work_order.technician_id = tech.id
                work_order.assignee_id = tech.id
                if data.collaborator_ids is not None:
                    _set_collaborators(db, work_order.id, data.collaborator_ids, primary_id=tech.id)
            elif not work_order.technician_id:
                raise HTTPException(status_code=400, detail="派工必须指定维修员（technician_id）")
        elif is_technician:
            if not data.technician_id:
                raise HTTPException(status_code=400, detail="领取任务请把自己设为接收人（technician_id=本人）")
            tech = db.query(User).filter(User.id == data.technician_id).first()
            if not tech or not tech.is_active:
                raise HTTPException(status_code=400, detail="接收人不存在或已停用")

            # 判断工单当前是否真的"有人负责"：负责人必须是 TECHNICIAN 才算被派
            current_owner = None
            if work_order.technician_id:
                owner = db.query(User).filter(User.id == work_order.technician_id).first()
                if owner and owner.role == UserRole.TECHNICIAN.value and owner.is_active:
                    current_owner = owner

            if data.technician_id == current_user.id:
                # 抢单：工单还没人负责（或本来就归自己）
                if current_owner and current_owner.id != current_user.id:
                    raise HTTPException(
                        status_code=403,
                        detail=f"该工单已派给 {current_owner.real_name}，不能重复领取")
                work_order.technician_id = current_user.id
                work_order.assignee_id = current_user.id
            else:
                # 转派：只有当前负责人可以把自己名下的工单转给别人
                if not current_owner or current_owner.id != current_user.id:
                    raise HTTPException(status_code=403, detail="只有当前负责人可以转派该工单")
                if tech.role != UserRole.TECHNICIAN.value:
                    raise HTTPException(status_code=400, detail="只能转派给维修员")
                work_order.technician_id = tech.id
                work_order.assignee_id = tech.id
                if data.collaborator_ids is not None:
                    _set_collaborators(db, work_order.id, data.collaborator_ids, primary_id=tech.id)
        else:
            raise HTTPException(status_code=403, detail="仅主管/管理员可派工，维修员可领取或转派")

    old_technician_id = work_order.technician_id
    from_status_enum = work_order.status

    # 拒收回池：清空负责人（old_technician_id 已用于工作量回退）
    if to_status_val == WorkOrderStatus.SUBMITTED.value and from_status_val == WorkOrderStatus.ASSIGNED.value:
        work_order.technician_id = None
        work_order.assignee_id = None
        work_order.dispatched_at = None
        db.query(WorkOrderCollaborator).filter(
            WorkOrderCollaborator.work_order_id == work_order.id
        ).delete(synchronize_session=False)

    # 派工/改派：记录分配人（谁把单分出去的）
    if to_status_val == WorkOrderStatus.ASSIGNED.value:
        work_order.dispatcher_id = current_user.id
        work_order.dispatched_at = datetime.now()

    if to_status_val == WorkOrderStatus.COMPLETED.value:
        try:
            complete_result = complete_work_order_internal(work_order_id, db)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"[Transition] 调用complete逻辑失败，继续手动标记完成: {e}")
            work_order.status = to_status_enum
            db.flush()
    else:
        work_order.status = to_status_enum
        db.flush()

    _add_progress_log(
        db=db,
        work_order_id=work_order.id,
        from_status=from_status_enum,
        to_status=to_status_enum,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        source=data.source or "WEB",
        remark=data.remark,
        location=data.location,
        attachments=data.attachments,
    )

    if from_status_val in WORKLOAD_INCREASE_STATUSES:
        _update_workload(db, old_technician_id, -1)
    if to_status_val in WORKLOAD_INCREASE_STATUSES:
        _update_workload(db, work_order.technician_id, +1)
    if to_status_val in WORKLOAD_DECREASE_STATUSES and from_status_val not in WORKLOAD_DECREASE_STATUSES:
        _update_workload(db, old_technician_id, -1)

    db.commit()
    db.refresh(work_order)

    if to_status_val == WorkOrderStatus.SUBMITTED.value and from_status_val == WorkOrderStatus.ASSIGNED.value:
        _notify_returned_to_pool(work_order, current_user, data.remark)

    # SLA：接单记首次响应；进入待归档视为维修完成；随后刷新 SLA 状态
    try:
        if to_status_val == WorkOrderStatus.ACCEPTED.value and not work_order.first_response_at:
            work_order.first_response_at = datetime.now()
        if to_status_val == WorkOrderStatus.ARCHIVING.value and not work_order.resolved_at:
            work_order.resolved_at = datetime.now()
        if work_order.used_parts or work_order.work_hours:
            sla_service.recompute_cost(work_order, db)
        sla_service.mark_overdue(work_order)
        # 告警级别随之刷新：优先级映射，SLA 超时升 P0
        _lv = AL.from_priority(work_order.priority)
        work_order.alert_level = "P0" if work_order.sla_status == "OVERDUE" else _lv
        db.commit()
    except Exception as e:
        logger.warning(f"[WorkOrder] SLA/成本刷新失败（忽略）: {e}")

    # 群机器人通知：提交报修 / 派工 / 退回
    # 拒收回池用专门的“被拒收”通知，避免再发一条“新报修待派工”
    if to_status_val == WorkOrderStatus.SUBMITTED.value and from_status_val == WorkOrderStatus.ASSIGNED.value:
        _event = None
    else:
        _event = {"SUBMITTED": "submitted", "ASSIGNED": "assigned", "REJECTED": "rejected"}.get(to_status_val)
    if _event:
        _notify_wo(work_order, _event, actor=current_user.real_name, extra=(data.remark or ""))

    # 状态变更后，异步刷新维修员钉钉上的派工进度卡片（Web 端操作实时反映到钉钉，不阻塞接口响应）
    # 钉钉卡片回调走 DINGTALK_CARD 来源，卡片已由 dingtalk_wo_card._dispatch_action 异步刷新，此处跳过避免重复。
    if data.source != "DINGTALK_CARD":
        try:
            from app.core.dingtalk_wo_card import _refresh_card_async
            from app.models.user import User as _User
            _tech = db.query(_User).filter(_User.id == work_order.technician_id).first()
            if _tech and _tech.dingtalk_userid:
                _refresh_card_async(work_order.id, work_order.work_order_no)
        except Exception as e:
            logger.warning(f"[Transition] 钉钉进度卡片刷新失败（不影响工单状态）: {e}")

    logger.info(f"[WorkOrder] 状态流转 #{work_order.id}: {from_status_val} → {to_status_val} by {current_user.real_name}")
    return _build_work_order_response(work_order, db)


def complete_work_order_internal(work_order_id: int, db: Session):
    work_order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")
    if work_order.status == WorkOrderStatus.COMPLETED:
        return work_order

    wo_data = {
        "fault_description": work_order.fault_description,
        "fault_code": work_order.fault_code,
        "fault_phenomenon": work_order.fault_phenomenon,
        "root_cause": work_order.root_cause,
        "solution_steps": work_order.solution_steps,
        "device_error_code": work_order.device_error_code,
        "device_type": getattr(work_order, "device_type", None),
        "log_text": work_order.log_text,
        "repair_result": work_order.repair_result,
        "work_hours": work_order.work_hours,
    }
    try:
        analysis = ticket_agent.analyze(wo_data)
        work_order.confidence = analysis.confidence
        work_order.analysis_result = {
            "device_type": analysis.device_type,
            "fault_category": analysis.fault_category,
            "severity": analysis.severity,
            "completeness_score": analysis.completeness_score,
            "missing_fields": analysis.missing_fields,
            "validation_notes": analysis.validation_notes,
            "raw_reasoning": analysis.raw_reasoning,
            "suggested_actions": analysis.suggested_actions,
            "standardized_fields": {
                "fault_code": analysis.standardized_fault_code,
                "fault_phenomenon": analysis.standardized_fault_phenomenon,
                "root_cause": analysis.standardized_root_cause,
                "solution_steps": analysis.standardized_solution_steps,
            },
        }
        if analysis.standardized_fault_code and not work_order.fault_code:
            work_order.fault_code = analysis.standardized_fault_code
        if analysis.standardized_fault_phenomenon and not work_order.fault_phenomenon:
            work_order.fault_phenomenon = analysis.standardized_fault_phenomenon
        if analysis.standardized_root_cause and not work_order.root_cause:
            work_order.root_cause = analysis.standardized_root_cause
        if analysis.standardized_solution_steps and not work_order.solution_steps:
            work_order.solution_steps = analysis.standardized_solution_steps
        if analysis.tags:
            work_order.tags = analysis.tags
    except Exception as e:
        logger.warning(f"[WorkOrder] 提交时 AI 分析失败: {e}")

    try:
        _auto_publish_knowledge(work_order, db)
    except Exception as e:
        logger.warning(f"[WorkOrder] 知识收录失败: {e}")

    try:
        _deduct_spare_parts(work_order, db)
    except Exception as e:
        logger.warning(f"[WorkOrder] 备件扣减失败: {e}")

    try:
        _ensure_fault_code_mappings(work_order, db)
    except Exception as e:
        logger.warning(f"[WorkOrder] 故障码映射失败: {e}")

    work_order.status = WorkOrderStatus.COMPLETED
    db.flush()
    logger.info(f"[WorkOrder] 工单 {work_order.work_order_no} 已完成(流转接口)")
    return work_order


# ========== 工单归档：关键字段齐全性校验 + 归档完成 ==========

ARCHIVE_REQUIRED_FIELDS = [
    ("fault_description", "故障描述"),
    ("fault_phenomenon", "故障现象"),
    ("root_cause", "根本原因"),
    ("solution_steps", "解决方案"),
    ("repair_result", "维修结果"),
    ("work_hours", "维修工时"),
]


def _archive_field_check(work_order: WorkOrder) -> dict:
    """校验工单归档关键字段是否齐全。返回 {passed, missing_fields, completeness, total_fields}"""
    missing = []
    for field, label in ARCHIVE_REQUIRED_FIELDS:
        val = getattr(work_order, field, None)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(label)
    total = len(ARCHIVE_REQUIRED_FIELDS)
    filled = total - len(missing)
    return {
        "passed": len(missing) == 0,
        "missing_fields": missing,
        "completeness": round(filled / total, 2),
        "total_fields": total,
    }


class HoldIn(BaseModel):
    reason: str = Field(..., max_length=20, description="VENDOR/SPARE/CUSTOMER/IDC/OTHER")
    remark: Optional[str] = None


class RmaIn(BaseModel):
    vendor: Optional[str] = None
    rma_no: Optional[str] = None
    status: Optional[str] = None
    shipped_at: Optional[datetime] = None
    vendor_received_at: Optional[datetime] = None
    returned_at: Optional[datetime] = None
    replacement_sn: Optional[str] = None
    remark: Optional[str] = None


HOLD_LABELS = {"VENDOR": "等厂商", "SPARE": "等备件", "CUSTOMER": "等客户", "IDC": "等 IDC", "OTHER": "其他"}


def _can_operate(wo: WorkOrder, user: User) -> bool:
    return (user.role in (UserRole.ADMIN.value, UserRole.SUPERVISOR.value)
            or wo.technician_id == user.id or wo.assignee_id == user.id)


@router.post("/{work_order_id}/hold", summary="挂起工单（等厂商/备件/客户/IDC）")
def hold_work_order(work_order_id: int, data: HoldIn,
                    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    wo = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    if not _can_operate(wo, current_user):
        raise HTTPException(status_code=403, detail="仅负责人、主管或管理员可挂起")
    if wo.is_on_hold:
        raise HTTPException(status_code=400, detail="工单已在挂起中")
    active = {WorkOrderStatus.ACCEPTED.value, WorkOrderStatus.ARRIVED.value,
              WorkOrderStatus.INSPECTING.value, WorkOrderStatus.IN_PROGRESS.value}
    status_val = wo.status.value if hasattr(wo.status, "value") else str(wo.status)
    if status_val not in active:
        raise HTTPException(status_code=400, detail="当前状态不能挂起")
    reason = (data.reason or "OTHER").upper()
    if reason not in HOLD_LABELS:
        reason = "OTHER"
    wo.is_on_hold = True
    wo.hold_reason = reason
    wo.hold_remark = data.remark
    wo.hold_started_at = datetime.now()
    wo.sla_status = "ON_HOLD"
    db.add(WorkOrderProgressLog(
        work_order_id=wo.id, from_status=wo.status, to_status=wo.status,
        operator_id=current_user.id, operator_name=current_user.real_name,
        source="WEB", remark=f"挂起：{HOLD_LABELS[reason]} {data.remark or ''}".strip(),
    ))
    db.commit()
    return {"message": "已挂起，SLA 暂停计时", "hold_reason": reason,
            "hold_label": HOLD_LABELS[reason]}


@router.post("/{work_order_id}/resume", summary="恢复挂起的工单")
def resume_work_order(work_order_id: int,
                      db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    wo = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    if not _can_operate(wo, current_user):
        raise HTTPException(status_code=403, detail="仅负责人、主管或管理员可恢复")
    if not wo.is_on_hold:
        raise HTTPException(status_code=400, detail="工单未挂起")
    now = datetime.now()
    minutes = 0
    if wo.hold_started_at:
        minutes = max(0, int((now - wo.hold_started_at).total_seconds() // 60))
    wo.hold_total_minutes = int(wo.hold_total_minutes or 0) + minutes
    if wo.response_due_at:
        wo.response_due_at = wo.response_due_at + timedelta(minutes=minutes)
    if wo.resolve_due_at:
        wo.resolve_due_at = wo.resolve_due_at + timedelta(minutes=minutes)
    wo.is_on_hold = False
    wo.hold_started_at = None
    try:
        info = sla_service.evaluate(wo)
        wo.sla_status = info["sla_status"]
    except Exception:
        wo.sla_status = "ON_TIME"
    db.add(WorkOrderProgressLog(
        work_order_id=wo.id, from_status=wo.status, to_status=wo.status,
        operator_id=current_user.id, operator_name=current_user.real_name,
        source="WEB", remark=f"恢复处理（本次挂起 {minutes} 分钟，累计 {wo.hold_total_minutes} 分钟）",
    ))
    db.commit()
    return {"message": "已恢复，SLA 继续计时", "hold_minutes": minutes,
            "hold_total_minutes": wo.hold_total_minutes, "sla_status": wo.sla_status}


@router.put("/{work_order_id}/rma", summary="更新 RMA / 厂商返修进度")
def update_rma(work_order_id: int, data: RmaIn,
               db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    wo = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not wo:
        raise HTTPException(status_code=404, detail="工单不存在")
    if not _can_operate(wo, current_user):
        raise HTTPException(status_code=403, detail="仅负责人、主管或管理员可更新 RMA")
    mapping = {
        "rma_vendor": data.vendor, "rma_no": data.rma_no, "rma_status": data.status,
        "rma_shipped_at": data.shipped_at, "rma_vendor_received_at": data.vendor_received_at,
        "rma_returned_at": data.returned_at, "rma_replacement_sn": data.replacement_sn,
        "rma_remark": data.remark,
    }
    for key, val in mapping.items():
        if val is not None:
            setattr(wo, key, val)
    if data.vendor or data.rma_no:
        wo.need_rma = True
        if (wo.service_mode or "") != "SITE":
            wo.service_mode = "RMA"
    db.add(WorkOrderProgressLog(
        work_order_id=wo.id, from_status=wo.status, to_status=wo.status,
        operator_id=current_user.id, operator_name=current_user.real_name,
        source="WEB",
        remark=f"更新 RMA：{wo.rma_vendor or '-'} / {wo.rma_no or '-'} / {wo.rma_status or '-'}",
    ))
    db.commit()
    return {"message": "RMA 信息已保存", "rma_venue": wo.rma_vendor,
            "rma_no": wo.rma_no, "rma_status": wo.rma_status}


@router.post("/{work_order_id}/archive-check", summary="工单归档校验（关键字段齐全性）")
def archive_check(
    work_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """待归档工单的归档校验：检查关键字段是否齐全，返回完成度与缺失项。"""
    work_order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")
    if work_order.status != WorkOrderStatus.ARCHIVING:
        raise HTTPException(status_code=400, detail="仅待归档状态工单可执行归档校验")

    is_admin = current_user.role == UserRole.ADMIN.value
    is_assigned_tech = work_order.technician_id == current_user.id or work_order.assignee_id == current_user.id
    if not (is_assigned_tech or is_admin):
        raise HTTPException(status_code=403, detail="仅被指派的维修员或管理员可归档")

    result = _archive_field_check(work_order)
    logger.info(
        f"[Archive] 归档校验 #{work_order_id}: passed={result['passed']}, "
        f"completeness={result['completeness']}, missing={result['missing_fields']} by {current_user.real_name}"
    )
    return result


@router.post("/{work_order_id}/archive-complete", summary="工单归档完成（校验达标后归档）")
def archive_complete(
    work_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """归档完成：必须通过关键字段齐全性校验（完成度达标）才允许，否则拒绝并列出缺失项。"""
    work_order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")
    if work_order.status != WorkOrderStatus.ARCHIVING:
        raise HTTPException(status_code=400, detail="仅待归档状态工单可执行归档完成")

    is_admin = current_user.role == UserRole.ADMIN.value
    is_assigned_tech = work_order.technician_id == current_user.id or work_order.assignee_id == current_user.id
    if not (is_assigned_tech or is_admin):
        raise HTTPException(status_code=403, detail="仅被指派的维修员或管理员可归档")

    if work_order.customer_id and work_order.customer_accept_status != "ACCEPTED":
        raise HTTPException(status_code=400, detail="客户尚未确认解决，请客户在门户确认后再归档")
    result = _archive_field_check(work_order)
    if not result["passed"]:
        logger.warning(
            f"[Archive] 归档完成被拒绝 #{work_order_id}: missing={result['missing_fields']} by {current_user.real_name}"
        )
        raise HTTPException(
            status_code=400,
            detail=f"归档完成度不足（{result['completeness']:.0%}），缺失字段：{'、'.join(result['missing_fields'])}",
        )

    from_status_enum = work_order.status
    work_order.status = WorkOrderStatus.ARCHIVED
    db.flush()
    _add_progress_log(
        db=db,
        work_order_id=work_order.id,
        from_status=from_status_enum,
        to_status=WorkOrderStatus.ARCHIVED,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        source="WEB",
        remark=f"工单归档完成（完成度 {result['completeness']:.0%}）",
    )
    try:
        _auto_publish_knowledge(work_order, db)
    except Exception as e:
        logger.warning(f"[Archive] 归档时知识收录失败: {e}")
    try:
        _ensure_fault_code_mappings(work_order, db)
    except Exception as e:
        logger.warning(f"[Archive] 归档时故障码映射失败: {e}")

    db.commit()
    db.refresh(work_order)
    logger.info(f"[Archive] 工单归档完成 #{work_order_id}: {work_order.work_order_no} by {current_user.real_name}")
    _notify_wo(work_order, "archived", actor=current_user.real_name,
               extra=f"归档完成度 {result['completeness']:.0%}")
    return {
        "archived": True,
        "work_order_id": work_order.id,
        "work_order_no": work_order.work_order_no,
        "status": WorkOrderStatus.ARCHIVED.value,
        "completeness": result["completeness"],
    }


@router.post("/{work_order_id}/feedback", summary="报修人回访评价（1-5 分）")
def submit_feedback(
    work_order_id: int,
    data: WorkOrderFeedbackIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    work_order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")
    if work_order.status not in (WorkOrderStatus.COMPLETED, WorkOrderStatus.ARCHIVED):
        raise HTTPException(status_code=400, detail="仅已完成/已归档的工单可评价")
    if data.score < 1 or data.score > 5:
        raise HTTPException(status_code=400, detail="评分需在 1-5 之间")
    is_admin = current_user.role == UserRole.ADMIN.value
    if not is_admin and current_user.id not in (work_order.created_by, work_order.reporter_id, work_order.technician_id):
        raise HTTPException(status_code=403, detail="仅报修人、维修员或管理员可评价")

    work_order.satisfaction_score = data.score
    work_order.satisfaction_comment = (data.comment or "").strip() or None
    work_order.feedback_at = datetime.now()
    db.commit()
    logger.info(f"[WorkOrder] 回访评价 #{work_order_id}: {data.score} 分 by {current_user.real_name}")
    return {"message": "评价已提交", "score": work_order.satisfaction_score,
            "comment": work_order.satisfaction_comment}


@router.get("/{work_order_id}/progress", summary="获取工单进度日志")
def get_work_order_progress(
    work_order_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    work_order = db.query(WorkOrder).filter(WorkOrder.id == work_order_id).first()
    if not work_order:
        raise HTTPException(status_code=404, detail="工单不存在")

    current_status_val = work_order.status.value if work_order.status else None
    allowed_next = VALID_TRANSITIONS.get(current_status_val, [])

    logs = (
        db.query(WorkOrderProgressLog)
        .filter(WorkOrderProgressLog.work_order_id == work_order_id)
        .order_by(WorkOrderProgressLog.created_at.asc())
        .all()
    )

    log_responses = [
        WorkOrderProgressLogResponse(
            id=l.id,
            work_order_id=l.work_order_id,
            from_status=l.from_status.value if l.from_status else None,
            to_status=l.to_status.value if l.to_status else None,
            operator_id=l.operator_id,
            operator_name=l.operator_name,
            source=l.source,
            remark=l.remark,
            location=l.location,
            attachments=l.attachments,
            created_at=l.created_at,
        )
        for l in logs
    ]

    return {
        "work_order_id": work_order_id,
        "current_status": current_status_val,
        "allowed_next": allowed_next,
        "progress_logs": log_responses,
    }


@router.post("/from-dispatch", response_model=WorkOrderResponse, summary="从派工创建工单(主管)")
def create_work_order_from_dispatch(
    data: WorkOrderDispatchCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role not in (UserRole.SUPERVISOR.value, UserRole.ADMIN.value):
        raise HTTPException(status_code=403, detail="仅主管或管理员可通过派工创建工单")

    technician = db.query(User).filter(User.id == data.technician_id).first()
    if not technician:
        raise HTTPException(status_code=400, detail="指派的维修员不存在")
    if not technician.is_active:
        raise HTTPException(status_code=400, detail="指派的维修员已停用")
    if technician.role not in (UserRole.TECHNICIAN.value, UserRole.ADMIN.value):
        raise HTTPException(status_code=400, detail="被指派人必须是维修员角色")

    # 在岗校验：查询当天该维修员的排班/请假记录
    today = date.today()
    duty_schedules = (
        db.query(DutySchedule)
        .filter(DutySchedule.date == today, DutySchedule.user_id == data.technician_id)
        .all()
    )
    # 1. 全天请假 → 阻止派工
    for ds in duty_schedules:
        if ds.schedule_type == 'LEAVE' and ds.shift == 'ALL_DAY':
            raise HTTPException(status_code=400, detail="该维修员今日全天请假，无法派工")
    # 2. 当前时段请假 → 阻止派工
    current_shift = _get_current_shift()
    for ds in duty_schedules:
        if ds.schedule_type == 'LEAVE' and ds.shift == current_shift:
            raise HTTPException(
                status_code=400,
                detail=f"该维修员当前时段请假（{current_shift}），无法派工",
            )
    # 3. 无任何排班记录 → 仅警告，允许临时派工
    if not duty_schedules:
        logger.warning(
            f"[WorkOrder] 维修员 #{data.technician_id} 今日无排班记录，允许临时派工"
        )

    today_str = date.today().strftime("%Y%m%d")
    prefix = f"WO-{today_str}-"
    latest = (
        db.query(WorkOrder)
        .filter(WorkOrder.work_order_no.like(f"{prefix}%"))
        .order_by(WorkOrder.work_order_no.desc())
        .first()
    )
    if latest and latest.work_order_no:
        try:
            seq = int(latest.work_order_no.split("-")[-1]) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    work_order_no = f"{prefix}{seq:03d}"

    work_order = WorkOrder(
        work_order_no=work_order_no,
        device_id=data.device_id,
        device_code=data.device_code,
        fault_code=data.fault_code,
        fault_description=data.fault_description,
        fault_category=data.fault_category,
        fault_phenomenon_type=data.fault_phenomenon_type,
        fault_phenomenon=data.fault_phenomenon,
        fault_media=data.fault_media,
        priority=data.priority or "MEDIUM",
        location=data.location,
        technician_id=data.technician_id,
        assignee_id=data.technician_id,
        tags=data.tags,
        status=WorkOrderStatus.ASSIGNED,
        created_by=current_user.id,
        dispatcher_id=current_user.id,
        dispatched_at=datetime.now(),
    )
    db.add(work_order)
    db.flush()
    _set_collaborators(db, work_order.id, data.collaborator_ids, primary_id=data.technician_id)

    _add_progress_log(
        db=db,
        work_order_id=work_order.id,
        from_status=WorkOrderStatus.DRAFT,
        to_status=WorkOrderStatus.ASSIGNED,
        operator_id=current_user.id,
        operator_name=current_user.real_name,
        source="WEB",
        remark=f"主管派工创建工单，指派给 {technician.real_name}",
    )

    _update_workload(db, data.technician_id, +1)

    # ===== 系统站内通知 =====
    device_desc = data.device_code or (f"设备#{data.device_id}" if data.device_id else "未指定设备")
    try:
        from app.api.notifications import create_notification
        create_notification(
            db,
            user_id=data.technician_id,
            type="work_order",
            title=f"新工单派工通知",
            content=f"工单 {work_order_no} 已派发给您，设备：{device_desc}，故障：{(data.fault_description or '')[:60]}",
            work_order_id=work_order.id,
            level=AL.from_priority(getattr(work_order, 'priority', None)),
        )
        for cu in (db.query(User)
                   .join(WorkOrderCollaborator, WorkOrderCollaborator.user_id == User.id)
                   .filter(WorkOrderCollaborator.work_order_id == work_order.id).all()):
            if cu.id == data.technician_id:
                continue
            create_notification(
                db,
                user_id=cu.id,
                type="work_order",
                title="工单协作通知",
                content=f"你被加入工单 {work_order_no}（{device_desc}）协作。故障：{(data.fault_description or '')[:60]}",
                work_order_id=work_order.id,
                level=AL.from_priority(getattr(work_order, 'priority', None)),
            )
        logger.info(f"[Notification] 站内通知已写入: 工单{work_order_no} → 维修员#{data.technician_id}")
    except Exception as e:
        logger.warning(f"[Notification] 站内通知写入失败（不影响工单创建）: {e}")

    # ===== 钉钉通知（异步）：发送带进度确认按钮的互动卡片 =====
    def _send_dingtalk_dispatch(technician_userid, wo, sup_name):
        try:
            from app.core.dingtalk_wo_card import send_progress_card
            from app.core.config import settings
            public_url = getattr(settings, "SERVER_PUBLIC_URL", "") or ""
            send_progress_card(
                technician_userid,
                wo,
                supervisor_name=sup_name,
                public_url=public_url,
            )
        except Exception as e:
            logger.warning(f"[DingTalk] 派工进度卡片发送失败（不影响工单创建）: {e}")

    background_tasks.add_task(
        _send_dingtalk_dispatch,
        technician.dingtalk_userid or "",
        work_order,
        current_user.real_name,
    )

    db.commit()
    db.refresh(work_order)
    logger.info(f"[WorkOrder] 主管派工创建 {work_order_no} → 技术员 #{data.technician_id}({technician.real_name})")
    return _build_work_order_response(work_order, db)


def _build_work_order_response(work_order: WorkOrder, db: Session) -> WorkOrderResponse:
    resp = WorkOrderResponse.model_validate(work_order)
    # 对外 6 状态分组
    resp.status_group = SG.group_of(work_order.status)
    resp.status_group_label = SG.label_of(work_order.status)
    # 告警级别：优先级映射；SLA 超时升到 P0
    lv = AL.from_priority(getattr(work_order, 'priority', None))
    if getattr(work_order, 'sla_status', None) == 'OVERDUE':
        lv = 'P0'
    resp.alert_level = lv
    if work_order.created_by:
        creator = db.query(User).filter(User.id == work_order.created_by).first()
        resp.created_by_employee_id = creator.employee_id if creator else None
    if work_order.technician_id:
        tech = db.query(User).filter(User.id == work_order.technician_id).first()
        resp.technician_name = tech.real_name if tech else None
    # 是否为“别人转派给我”的单：从最近一条「改派：A → B」进度日志取原负责人
    try:
        if work_order.status == WorkOrderStatus.ASSIGNED and work_order.progress_logs:
            for l in sorted(work_order.progress_logs, key=lambda x: x.id or 0, reverse=True):
                remark = (l.remark or "")
                if remark.startswith("改派：") and "→" in remark:
                    resp.transfer_from_name = remark.split("：", 1)[1].split("→")[0].strip()
                    break
    except Exception:
        resp.transfer_from_name = None
    resp.collaborators = _collaborators_of(db, work_order.id)
    if work_order.progress_logs:
        resp.progress_logs = [
            WorkOrderProgressLogResponse(
                id=l.id,
                work_order_id=l.work_order_id,
                from_status=l.from_status.value if l.from_status else None,
                to_status=l.to_status.value if l.to_status else None,
                operator_id=l.operator_id,
                operator_name=l.operator_name,
                source=l.source,
                remark=l.remark,
                location=l.location,
                attachments=l.attachments,
                created_at=l.created_at,
            )
            for l in work_order.progress_logs
        ]
    return resp

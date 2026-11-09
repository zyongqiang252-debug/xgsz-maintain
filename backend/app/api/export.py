"""报表导出：工单 / 备件 / 知识 / 出入库流水 → Excel

用 openpyxl 内存生成，不落临时文件；文件名带日期。
"""
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_supervisor
from app.models.device import Device
from app.models.knowledge import KnowledgeItem
from app.models.spare_part import SparePart
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.models.work_order import WorkOrder

router = APIRouter(tags=["报表导出"], dependencies=[Depends(require_supervisor)])

_HEAD_FILL = PatternFill("solid", fgColor="0FC6C2")
_HEAD_FONT = Font(bold=True, color="FFFFFF")


def _xlsx(title: str, headers, rows) -> StreamingResponse:
    wb = Workbook()
    ws = wb.active
    ws.title = title
    ws.append(list(headers))
    for c in ws[1]:
        c.fill = _HEAD_FILL
        c.font = _HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
    for r in rows:
        ws.append(list(r))
    # 列宽自适应（按内容长度，最多 40）
    for i, col in enumerate(ws.columns, start=1):
        width = max((len(str(c.value or "")) for c in col), default=8)
        ws.column_dimensions[chr(64 + i) if i <= 26 else "A"].width = min(40, max(8, width + 2))
    ws.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    # HTTP 头只能是 latin-1：中文名用 RFC 5987 的 filename* 传，另给一个 ASCII 兜底名
    from urllib.parse import quote
    cn_name = f"{title}-{stamp}.xlsx"
    ascii_name = f"export-{stamp}.xlsx"
    disp = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(cn_name)}"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": disp},
    )


def _status_cn(s) -> str:
    return {
        "DRAFT": "草稿", "SUBMITTED": "已提交", "ASSIGNED": "已派工", "ACCEPTED": "已接单",
        "ARRIVED": "已到场", "INSPECTING": "检查中", "IN_PROGRESS": "维修中",
        "ARCHIVING": "待归档", "ARCHIVED": "已归档", "COMPLETED": "已完成",
        "REJECTED": "已退回",
    }.get(s, s or "")


@router.get("/work-orders.xlsx", summary="导出工单（Excel）")
def export_work_orders(
    status: str = Query(None, description="按状态筛选"),
    date_from: date = Query(None),
    date_to: date = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(WorkOrder)
    if status:
        q = q.filter(WorkOrder.status == status)
    if date_from:
        q = q.filter(WorkOrder.created_at >= datetime.combine(date_from, datetime.min.time()))
    if date_to:
        q = q.filter(WorkOrder.created_at <= datetime.combine(date_to, datetime.max.time()))
    rows = q.order_by(WorkOrder.created_at.desc()).limit(5000).all()
    tech_names = {u.id: u.real_name for u in db.query(User).all()}

    data = []
    for w in rows:
        data.append([
            w.work_order_no,
            _status_cn(w.status.value if hasattr(w.status, "value") else w.status),
            w.device_code or "",
            (w.fault_description or "").replace("\n", " ")[:200],
            w.fault_category or "",
            w.priority or "",
            tech_names.get(w.technician_id, ""),
            w.location or "",
            (w.root_cause or "")[:150],
            (w.solution_steps or "").replace("\n", " ")[:200],
            w.work_hours or "",
            w.labor_cost or "",
            w.parts_cost or "",
            w.total_cost or "",
            w.sla_status or "",
            w.satisfaction_score or "",
            w.created_at.strftime("%Y-%m-%d %H:%M") if w.created_at else "",
            w.resolved_at.strftime("%Y-%m-%d %H:%M") if w.resolved_at else "",
        ])
    headers = ["工单号", "状态", "设备编码", "故障描述", "故障分类", "优先级", "维修员", "位置",
               "根本原因", "解决方案", "工时(h)", "人工成本", "备件成本", "总成本",
               "SLA", "满意度", "创建时间", "完成时间"]
    return _xlsx("工单", headers, data)


@router.get("/spare-parts.xlsx", summary="导出备件台账（Excel）")
def export_spare_parts(db: Session = Depends(get_db)):
    rows = db.query(SparePart).order_by(SparePart.part_code).all()
    data = [[p.part_code, p.part_name, p.specification or "", p.unit or "",
             p.stock_quantity or 0, p.safety_stock or 0, p.unit_price or 0,
             round((p.stock_quantity or 0) * (p.unit_price or 0), 2),
             p.location or "", p.supplier or ""] for p in rows]
    headers = ["编码", "名称", "规格型号", "单位", "库存", "安全库存", "单价", "库存金额", "存放位置", "供应商"]
    return _xlsx("备件台账", headers, data)


@router.get("/knowledge.xlsx", summary="导出知识库（Excel）")
def export_knowledge(db: Session = Depends(get_db)):
    rows = db.query(KnowledgeItem).order_by(KnowledgeItem.id.desc()).limit(5000).all()
    data = [[k.id, k.title or "", k.device_type or "", k.fault_code or "",
             (k.content or "").replace("\n", " ")[:500],
             k.status.value if hasattr(k.status, "value") else (k.status or ""),
             k.created_at.strftime("%Y-%m-%d %H:%M") if k.created_at else ""] for k in rows]
    headers = ["ID", "标题", "设备类型", "故障码", "内容摘要", "状态", "创建时间"]
    return _xlsx("知识库", headers, data)


@router.get("/stock-movements.xlsx", summary="导出出入库流水（Excel）")
def export_stock_movements(db: Session = Depends(get_db)):
    rows = db.query(StockMovement).order_by(StockMovement.created_at.desc()).limit(5000).all()
    type_cn = {"IN": "入库", "OUT": "出库", "ADJUST": "盘点", "RETURN": "退回"}
    data = [[m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
             type_cn.get(m.movement_type, m.movement_type),
             m.part_code or "", m.part_name or "", m.quantity,
             m.before_qty, m.after_qty, m.unit_price, m.amount,
             m.work_order_id or "", m.operator_name or "", m.remark or ""] for m in rows]
    headers = ["时间", "类型", "备件编码", "备件名称", "数量", "变动前", "变动后",
               "单价", "金额", "工单ID", "操作人", "备注"]
    return _xlsx("出入库流水", headers, data)


@router.get("/devices.xlsx", summary="导出服务器台账（Excel）")
def export_devices(db: Session = Depends(get_db)):
    rows = db.query(Device).order_by(Device.device_code).all()
    data = [[d.device_code, d.device_name, d.device_type or "", d.model or "", d.serial_no or "",
             d.room or "", d.rack_no or "", d.rack_unit or "", d.bmc_ip or "", d.business_ip or "",
             d.gpu_model or "", d.gpu_count or "", d.driver_version or "", d.cuda_version or "",
             d.firmware_version or "", d.alert_level or "", d.run_status or ""] for d in rows]
    headers = ["设备编码", "名称", "类型", "整机型号", "序列号SN", "机房", "机柜", "U位",
               "BMC IP", "业务 IP", "GPU 型号", "GPU 数量", "驱动版本", "CUDA", "固件版本",
               "告警级别", "运行状态"]
    return _xlsx("服务器台账", headers, data)

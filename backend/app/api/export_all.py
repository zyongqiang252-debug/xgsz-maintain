"""一键导出：单个工作簿 7 个 Sheet（工单/设备/备件/流水/知识/保养/点检）

与单表导出（export.py）共用卡片样式；一次请求拿全量数据。
"""
import io
from datetime import datetime
from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_supervisor
from app.models.device import Device
from app.models.knowledge import KnowledgeItem
from app.models.maintenance import InspectionRecord, MaintenancePlan, MaintenanceRecord
from app.models.spare_part import SparePart
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.models.work_order import WorkOrder

router = APIRouter(tags=["一键导出"], dependencies=[Depends(require_supervisor)])

_HEAD_FILL = PatternFill("solid", fgColor="0FC6C2")
_HEAD_FONT = Font(bold=True, color="FFFFFF")

STATUS_CN = {
    "DRAFT": "草稿", "SUBMITTED": "待派工", "ASSIGNED": "已派单", "ACCEPTED": "已接单",
    "ARRIVED": "已到场", "INSPECTING": "检查中", "IN_PROGRESS": "维修中",
    "ARCHIVING": "待归档", "ARCHIVED": "已归档", "COMPLETED": "已完成", "REJECTED": "已退回",
}
SERVICE_CN = {"REMOTE": "远程处理", "SITE": "现场处理", "RMA": "返厂维修"}


def _sheet(wb: Workbook, title: str, headers, rows):
    ws = wb.create_sheet(title=title)
    ws.append(list(headers))
    for c in ws[1]:
        c.fill = _HEAD_FILL
        c.font = _HEAD_FONT
        c.alignment = Alignment(horizontal="center", vertical="center")
    for r in rows:
        ws.append(list(r))
    for i, col in enumerate(ws.columns, start=1):
        width = max((len(str(c.value or "")) for c in col), default=8)
        letter = ws.cell(row=1, column=i).column_letter
        ws.column_dimensions[letter].width = min(40, max(8, width + 2))
    ws.freeze_panes = "A2"
    return ws


@router.get("/all.xlsx", summary="一键导出全部数据（7 个 Sheet）")
def export_all(db: Session = Depends(get_db)):
    wb = Workbook()
    wb.remove(wb.active)  # 去掉空白 Sheet

    users = {u.id: u.real_name for u in db.query(User).all()}

    # 1) 工单
    orders = db.query(WorkOrder).order_by(WorkOrder.created_at.desc()).limit(20000).all()
    _sheet(wb, "工单",
           ["工单号", "状态", "告警级别", "优先级", "服务器", "故障GPU", "故障件SN", "服务方式",
            "是否返厂", "故障描述", "故障大类", "维修员", "工时(h)", "人工成本", "备件成本", "总成本",
            "SLA", "满意度", "创建时间", "完成时间"],
           [[w.work_order_no,
             STATUS_CN.get(w.status.value if hasattr(w.status, "value") else w.status, w.status),
             w.sla_status or "", w.priority or "", w.device_code or "", w.gpu_index or "",
             w.fault_device_sn or "", SERVICE_CN.get(w.service_mode or "", w.service_mode or ""),
             "是" if w.need_rma else ("否" if w.need_rma is False else ""),
             (w.fault_description or "").replace("\n", " ")[:200], w.fault_category or "",
             users.get(w.technician_id, ""), w.work_hours or "",
             w.labor_cost or "", w.parts_cost or "", w.total_cost or "",
             w.sla_status or "", w.satisfaction_score or "",
             w.created_at.strftime("%Y-%m-%d %H:%M") if w.created_at else "",
             w.resolved_at.strftime("%Y-%m-%d %H:%M") if w.resolved_at else ""] for w in orders])

    # 2) 设备（服务器台账）
    devices = db.query(Device).order_by(Device.device_code).all()
    _sheet(wb, "设备台账",
           ["设备编码", "名称", "类型", "整机型号", "序列号SN", "厂商", "机房", "机柜", "U位",
            "BMC IP", "业务 IP", "GPU 型号", "GPU 数量", "驱动版本", "CUDA", "固件版本",
            "CPU", "内存(GB)", "操作系统", "告警级别", "运行状态", "项目"],
           [[d.device_code, d.device_name, d.device_type or "", d.model or "", d.serial_no or "",
             d.manufacturer or "", d.room or "", d.rack_no or "", d.rack_unit or "",
             d.bmc_ip or "", d.business_ip or "", d.gpu_model or "", d.gpu_count or "",
             d.driver_version or "", d.cuda_version or "", d.firmware_version or "",
             d.cpu_model or "", d.memory_gb or "", d.os_version or "",
             d.alert_level or "", d.run_status or "", d.project or ""] for d in devices])

    # 3) 备件
    parts = db.query(SparePart).order_by(SparePart.part_code).all()
    _sheet(wb, "备件台账",
           ["编码", "名称", "规格", "单位", "库存", "安全库存", "单价", "库存金额", "适用设备", "库位", "供应商"],
           [[p.part_code, p.part_name, p.specification or "", p.unit or "",
             p.stock_quantity or 0, p.safety_stock or 0, p.unit_price or 0,
             round((p.stock_quantity or 0) * (p.unit_price or 0), 2),
             p.device_type or "", p.location or "", p.supplier or ""] for p in parts])

    # 4) 出入库流水
    moves = db.query(StockMovement).order_by(StockMovement.created_at.desc()).limit(20000).all()
    type_cn = {"IN": "入库", "OUT": "出库", "ADJUST": "盘点", "RETURN": "退回"}
    _sheet(wb, "出入库流水",
           ["时间", "类型", "备件编码", "备件名称", "数量", "变动前", "变动后", "单价", "金额", "工单ID", "操作人", "备注"],
           [[m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
             type_cn.get(m.movement_type, m.movement_type), m.part_code or "", m.part_name or "",
             m.quantity, m.before_qty, m.after_qty, m.unit_price, m.amount,
             m.work_order_id or "", m.operator_name or "", m.remark or ""] for m in moves])

    # 5) 知识库
    kn = db.query(KnowledgeItem).order_by(KnowledgeItem.id.desc()).limit(10000).all()
    _sheet(wb, "知识库",
           ["ID", "标题", "设备类型", "故障码", "状态", "内容摘要", "创建时间"],
           [[k.id, k.title or "", k.device_type or "", k.fault_code or "",
             k.status.value if hasattr(k.status, "value") else (k.status or ""),
             (k.content or "").replace("\n", " ")[:500],
             k.created_at.strftime("%Y-%m-%d %H:%M") if k.created_at else ""] for k in kn])

    # 6) 保养计划
    plans = db.query(MaintenancePlan).order_by(MaintenancePlan.next_due_at).all()
    _sheet(wb, "保养计划",
           ["保养项目", "设备", "周期(天)", "上次完成", "下次到期", "状态", "负责人", "备注"],
           [[p.plan_name, p.device_code or "", p.cycle_value or "", 
             p.last_done_at.strftime("%Y-%m-%d") if p.last_done_at else "",
             p.next_due_at.strftime("%Y-%m-%d") if p.next_due_at else "",
             p.status or "", p.responsible_name or "", (p.remark or "")[:100]] for p in plans])

    # 7) 点检记录
    records = db.query(InspectionRecord).order_by(InspectionRecord.created_at.desc()).limit(20000).all()
    _sheet(wb, "点检记录",
           ["时间", "设备", "点检表", "点检人", "结果", "异常项", "备注"],
           [[r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "",
             r.device_code or "", r.template_name or "", r.inspector_name or "",
             "正常" if r.result == "OK" else "异常", r.abnormal_count or 0, r.remark or ""] for r in records])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    stamp = datetime.now().strftime("%Y%m%d%H%M")
    cn_name = f"芯光数智-全量数据-{stamp}.xlsx"
    ascii_name = f"xgsz-all-{stamp}.xlsx"
    disp = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(cn_name)}"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": disp},
    )

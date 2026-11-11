"""报表导出：工单 / 备件 / 知识 / 出入库流水 → Excel

用 openpyxl 内存生成，不落临时文件；文件名带日期。
"""
import io
from datetime import date, datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.device import Device
from app.models.knowledge import KnowledgeItem
from app.models.spare_part import SparePart
from app.models.stock_movement import StockMovement
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderStatus
from app.models.work_order_collaborator import WorkOrderCollaborator
from app.core import status_group as SG
from app.services import excel_style as X

router = APIRouter(tags=["报表导出"], dependencies=[Depends(get_current_user)])

def _xlsx(title: str, headers, rows, formats=None, wrap_cols=None, widths=None) -> StreamingResponse:
    """统一格式导出：标题行 + 品牌表头 + 斑马纹 + 冻结 + 筛选 + 打印设置"""
    wb = Workbook()
    wb.remove(wb.active)
    X.add_sheet(wb, title, headers, rows, formats=formats, wrap_cols=wrap_cols, widths=widths)

    stamp = datetime.now().strftime("%Y%m%d%H%M")
    cn_name = f"{title}-{stamp}.xlsx"
    ascii_name = f"export-{stamp}.xlsx"
    return StreamingResponse(
        io.BytesIO(X.workbook_bytes(wb)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers=X.filename_headers(cn_name, ascii_name),
    )


def _status_cn(s) -> str:
    """导出统一用 6 个业务状态文案"""
    return SG.label_of(s) if s else ""


@router.get("/work-orders.xlsx", summary="导出工单（Excel）")
def export_work_orders(
    status: str = Query(None, description="按状态筛选"),
    date_from: date = Query(None),
    date_to: date = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(WorkOrder)
    # 技术员只能导出自己相关 + 待派工池，与列表/详情口径一致
    role = (getattr(current_user.role, "value", current_user.role) or "").upper()
    if role == "TECHNICIAN":
        me = current_user.id
        collab_ids = (db.query(WorkOrderCollaborator.work_order_id)
                      .filter(WorkOrderCollaborator.user_id == me))
        q = q.filter(or_(
            WorkOrder.created_by == me,
            WorkOrder.reporter_id == me,
            WorkOrder.technician_id == me,
            WorkOrder.assignee_id == me,
            WorkOrder.id.in_(collab_ids),
            and_(WorkOrder.status == WorkOrderStatus.SUBMITTED.value,
                 WorkOrder.technician_id.is_(None)),
        ))
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
            w.device_code or (f"涉及：{w.fault_object}" if w.fault_object else ""),
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
    return _xlsx("工单", headers, data,
                 formats={"工时(h)": "0.0", "人工成本": X.MONEY, "备件成本": X.MONEY,
                          "总成本": X.MONEY, "满意度": X.INT},
                 wrap_cols={"故障描述", "根本原因", "解决方案"},
                 widths={"工单号": 20, "状态": 10, "设备编码": 16, "故障描述": 42,
                         "根本原因": 32, "解决方案": 42, "创建时间": 18, "完成时间": 18})


@router.get("/spare-parts.xlsx", summary="导出备件台账（Excel）")
def export_spare_parts(db: Session = Depends(get_db)):
    rows = db.query(SparePart).order_by(SparePart.part_code).all()
    data = [[p.part_code, p.part_name, p.specification or "", p.unit or "",
             p.stock_quantity or 0, p.safety_stock or 0, p.unit_price or 0,
             round((p.stock_quantity or 0) * (p.unit_price or 0), 2),
             p.location or "", p.supplier or ""] for p in rows]
    headers = ["编码", "名称", "规格型号", "单位", "库存", "安全库存", "单价", "库存金额", "存放位置", "供应商"]
    return _xlsx("备件台账", headers, data,
                 formats={"库存": X.INT, "安全库存": X.INT, "单价": X.MONEY, "库存金额": X.MONEY},
                 widths={"编码": 16, "名称": 22, "规格型号": 26})


@router.get("/knowledge.xlsx", summary="导出知识库（Excel）")
def export_knowledge(db: Session = Depends(get_db)):
    rows = db.query(KnowledgeItem).order_by(KnowledgeItem.id.desc()).limit(5000).all()
    data = [[k.id, k.title or "", k.device_type or "", k.fault_code or "",
             (k.content or "").replace("\n", " ")[:500],
             k.status.value if hasattr(k.status, "value") else (k.status or ""),
             k.created_at.strftime("%Y-%m-%d %H:%M") if k.created_at else ""] for k in rows]
    headers = ["ID", "标题", "设备类型", "故障码", "内容摘要", "状态", "创建时间"]
    return _xlsx("知识库", headers, data,
                 wrap_cols={"内容摘要"},
                 widths={"ID": 8, "标题": 34, "内容摘要": 60, "创建时间": 18})


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
    return _xlsx("出入库流水", headers, data,
                 formats={"数量": X.INT, "变动前": X.INT, "变动后": X.INT,
                          "单价": X.MONEY, "金额": X.MONEY},
                 widths={"时间": 18, "备件编码": 16, "备件名称": 22})


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
    return _xlsx("服务器台账", headers, data,
                 formats={"GPU 数量": X.INT},
                 widths={"设备编码": 16, "名称": 22, "序列号SN": 22, "BMC IP": 16,
                         "业务 IP": 16, "GPU 型号": 20})

"""工单 PDF 生成

用 reportlab + 系统中文字体（微软雅黑/宋体）排版 A4 工单，供打印/存档。
不落临时文件，直接返回内存字节流。
"""
import io
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)

# ---------- 字体 ----------
_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_CANDIDATES = [
    (r"C:\Windows\Fonts\msyh.ttc", 0, r"C:\Windows\Fonts\msyhbd.ttc", 0),
    (r"C:\Windows\Fonts\simsun.ttc", 0, r"C:\Windows\Fonts\simhei.ttf", None),
    (r"/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0, None, None),
]


def _register_font():
    """注册中文字体，失败则退回内置字体（中文会显示为方块）"""
    global _FONT, _FONT_BOLD
    for regular, idx, bold, bidx in _CANDIDATES:
        if not os.path.exists(regular):
            continue
        try:
            pdfmetrics.registerFont(TTFont("CN", regular, subfontIndex=idx))
            _FONT = "CN"
            if bold and os.path.exists(bold):
                pdfmetrics.registerFont(
                    TTFont("CN-B", bold, subfontIndex=bidx if bidx is not None else 0))
                _FONT_BOLD = "CN-B"
            else:
                _FONT_BOLD = "CN"
            return
        except Exception:
            continue


_register_font()

# ---------- 文案映射 ----------
STATUS_CN = {
    "DRAFT": "草稿", "SUBMITTED": "待派工", "ASSIGNED": "已派工", "ACCEPTED": "已接单",
    "ARRIVED": "已到场", "INSPECTING": "检查中", "IN_PROGRESS": "维修中",
    "ARCHIVING": "待归档", "ARCHIVED": "已归档", "COMPLETED": "已完成", "REJECTED": "已退回",
}
PRIORITY_CN = {"LOW": "低", "MEDIUM": "中", "HIGH": "高", "CRITICAL": "紧急"}
LEVEL_CN = {"P0": "P0 严重", "P1": "P1 重要", "P2": "P2 一般", "P3": "P3 提示"}
TYPE_CN = {"REPAIR": "报修", "MAINTENANCE": "保养", "INSPECTION": "点检", "IMPORT": "导入"}
SERVICE_CN = {"REMOTE": "远程处理", "SITE": "现场处理", "RMA": "返厂维修"}
RESULT_CN = {"PERMANENT_FIX": "彻底修复", "TEMPORARY_FIX": "临时处理", "UNABLE_FIX": "无法修复"}
SLA_CN = {"ON_TIME": "按时完成", "AT_RISK": "即将超时", "OVERDUE": "已超时"}

THEME = colors.HexColor("#0FC6C2")
GREY = colors.HexColor("#666666")
LINE = colors.HexColor("#DDDDDD")


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=ss["Title"], fontName=_FONT_BOLD,
                                fontSize=18, leading=24, spaceAfter=2, alignment=TA_CENTER),
        "sub": ParagraphStyle("sub", fontName=_FONT, fontSize=9, leading=13,
                              textColor=GREY, alignment=TA_CENTER, spaceAfter=8),
        "h": ParagraphStyle("h", fontName=_FONT_BOLD, fontSize=11, leading=16,
                            textColor=THEME, spaceBefore=8, spaceAfter=4),
        "body": ParagraphStyle("body", fontName=_FONT, fontSize=9, leading=14),
        "cell": ParagraphStyle("cell", fontName=_FONT, fontSize=8.5, leading=12),
        "cellb": ParagraphStyle("cellb", fontName=_FONT_BOLD, fontSize=8.5, leading=12),
        "small": ParagraphStyle("small", fontName=_FONT, fontSize=7.5, leading=10, textColor=GREY),
    }


def _fmt(dt):
    if not dt:
        return "—"
    if isinstance(dt, str):
        return dt[:16].replace("T", " ")
    return dt.strftime("%Y-%m-%d %H:%M")


def build_work_order_pdf(wo, technician_name=None, creator_name=None, progress_logs=None,
                         device_name=None) -> bytes:
    """生成工单 PDF 字节流"""
    st = _styles()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=16 * mm, rightMargin=16 * mm,
                            topMargin=14 * mm, bottomMargin=14 * mm,
                            title=f"维修工单 {wo.work_order_no}",
                            author="芯光数智")
    story = []

    # ===== 抬头 =====
    story.append(Paragraph("设备维修工单", st["title"]))
    story.append(Paragraph(
        f"工单号 {wo.work_order_no}　·　"
        f"{LEVEL_CN.get(wo.alert_level or 'P2', 'P2 一般')}　·　"
        f"{STATUS_CN.get(str(wo.status.value if hasattr(wo.status, 'value') else wo.status), '—')}",
        st["sub"]))

    # ===== 基本信息（两列） =====
    def cell(label, value, bold=False):
        return [
            Paragraph(label, st["cellb"]),
            Paragraph(str(value) if value not in (None, "") else "—", st["cell"]),
        ]

    left = [
        cell("工单类型", TYPE_CN.get(wo.order_type or "REPAIR", "报修")),
        cell("优先级", PRIORITY_CN.get(wo.priority or "MEDIUM", "中")),
        cell("服务器", wo.device_code or "—"),
        cell("设备名称", device_name or "—"),
        cell("故障GPU", wo.gpu_index or "—"),
        cell("故障件SN", wo.fault_device_sn or "—"),
        cell("服务方式", SERVICE_CN.get(wo.service_mode or "", "—")),
        cell("是否返厂", "是" if wo.need_rma else ("否" if wo.need_rma is False else "—")),
    ]
    right = [
        cell("报修人", creator_name or "—"),
        cell("维修员", technician_name or "—"),
        cell("创建时间", _fmt(wo.created_at)),
        cell("完成时间", _fmt(wo.resolved_at or wo.end_time)),
        cell("响应截止", _fmt(wo.response_due_at)),
        cell("修复截止", _fmt(wo.resolve_due_at)),
        cell("SLA 状态", SLA_CN.get(wo.sla_status or "", "—")),
        cell("当前位置", wo.location or "—"),
    ]

    grid = []
    for i in range(0, len(left), 2):
        a = left[i]
        b = left[i + 1] if i + 1 < len(left) else ["", ""]
        c = right[i]
        d = right[i + 1] if i + 1 < len(right) else ["", ""]
        grid.append([a[0], a[1], b[0], b[1], c[0], c[1], d[0], d[1]])

    tbl = Table(grid, colWidths=[16.5 * mm, 32.5 * mm, 16.5 * mm, 32.5 * mm, 16.5 * mm, 32.5 * mm, 16.5 * mm, 32.5 * mm])
    style = [
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F7F9FA")),
        ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F7F9FA")),
        ("BACKGROUND", (4, 0), (4, -1), colors.HexColor("#F7F9FA")),
        ("BACKGROUND", (6, 0), (6, -1), colors.HexColor("#F7F9FA")),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    tbl.setStyle(TableStyle(style))
    story.append(tbl)

    # ===== 文本段落 =====
    def section(title, text):
        if not text or not str(text).strip():
            return
        story.append(Paragraph(title, st["h"]))
        story.append(Paragraph(str(text).replace("\n", "<br/>"), st["body"]))

    section("故障描述", wo.fault_description)
    section("故障现象", wo.fault_phenomenon)
    section("根本原因", wo.root_cause)
    section("解决方案", wo.solution_steps)
    section("维修结果", RESULT_CN.get(wo.repair_result or "", wo.repair_result or ""))
    section("后续计划", wo.follow_up_plan)
    if wo.log_text:
        section("设备日志", wo.log_text)

    # ===== 备件清单 =====
    parts = wo.used_parts or []
    if parts:
        story.append(Paragraph("备件使用", st["h"]))
        rows = [[Paragraph("备件名称", st["cellb"]), Paragraph("编码", st["cellb"]),
                 Paragraph("数量", st["cellb"]), Paragraph("单价", st["cellb"]),
                 Paragraph("小计", st["cellb"])]]
        for p in parts:
            qty = p.get("quantity") or p.get("qty") or 0
            price = p.get("unit_price") or p.get("price") or 0
            rows.append([
                Paragraph(str(p.get("part_name") or p.get("name") or "—"), st["cell"]),
                Paragraph(str(p.get("part_code") or p.get("code") or "—"), st["cell"]),
                Paragraph(str(qty), st["cell"]),
                Paragraph(f"{price:g}" if isinstance(price, (int, float)) else str(price), st["cell"]),
                Paragraph(f"{(float(qty) * float(price)):.2f}" if isinstance(price, (int, float)) else "—", st["cell"]),
            ])
        pt = Table(rows, colWidths=[55 * mm, 40 * mm, 20 * mm, 30 * mm, 30 * mm])
        pt.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F7F9FA")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(pt)

    # ===== 费用 =====
    story.append(Paragraph("费用", st["h"]))
    cost_rows = [[
        Paragraph(f"工时 {wo.work_hours or 0:g} 小时", st["cell"]),
        Paragraph(f"人工成本 {wo.labor_cost or 0:.2f} 元", st["cell"]),
        Paragraph(f"备件成本 {wo.parts_cost or 0:.2f} 元", st["cell"]),
        Paragraph(f"<b>合计 {wo.total_cost or 0:.2f} 元</b>", st["cell"]),
    ]]
    ct = Table(cost_rows, colWidths=[40 * mm, 45 * mm, 45 * mm, 45 * mm])
    ct.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (3, 0), (3, 0), colors.HexColor("#F0FBFB")),
    ]))
    story.append(ct)

    # ===== 处理进度 =====
    if progress_logs:
        story.append(Paragraph("处理进度", st["h"]))
        rows = [[Paragraph("时间", st["cellb"]), Paragraph("环节", st["cellb"]),
                 Paragraph("操作人", st["cellb"]), Paragraph("说明", st["cellb"])]]
        for log in progress_logs:
            to = getattr(log, "to_status", None)
            to = to.value if hasattr(to, "value") else to
            rows.append([
                Paragraph(_fmt(getattr(log, "created_at", None)), st["cell"]),
                Paragraph(STATUS_CN.get(to or "", to or "—"), st["cell"]),
                Paragraph(getattr(log, "operator_name", None) or "—", st["cell"]),
                Paragraph((getattr(log, "remark", None) or "—")[:60], st["cell"]),
            ])
        lt = Table(rows, colWidths=[32 * mm, 25 * mm, 28 * mm, 80 * mm])
        lt.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F7F9FA")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(lt)

    # ===== 满意度 =====
    if wo.satisfaction_score:
        story.append(Paragraph("报修人评价", st["h"]))
        story.append(Paragraph(
            f"评分：{'★' * int(wo.satisfaction_score)}{'☆' * (5 - int(wo.satisfaction_score))}"
            f"（{wo.satisfaction_score}/5）　{wo.satisfaction_comment or ''}", st["body"]))

    # ===== 签字 =====
    story.append(Spacer(1, 10 * mm))
    sign = [[
        Paragraph("报修人签字：________________", st["cell"]),
        Paragraph("维修员签字：________________", st["cell"]),
        Paragraph("主管审核：________________", st["cell"]),
    ]]
    sg = Table(sign, colWidths=[60 * mm, 60 * mm, 60 * mm])
    sg.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(KeepTogether(sg))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        f"本工单由芯光数智 · 设备维修管理平台生成　打印时间 {datetime.now():%Y-%m-%d %H:%M}", st["small"]))

    doc.build(story)
    return buf.getvalue()

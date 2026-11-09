"""工单 PDF 生成（统一版式）

版式规范：
- A4，左右边距 18mm，正文宽 174mm；所有表格与段落严格对齐同一宽度
- 每页页眉：平台名 + 工单号；页脚：打印时间 + 第 X 页 / 共 Y 页
- 章节标题统一「▍标题」样式（品牌色竖条）
- 表格统一：表头浅色底、细边框、单元格内边距一致
- 文末签字栏 + 生成说明
"""
import io
import os
from datetime import datetime

from app.core import status_group as SG
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.platypus import (KeepTogether, Paragraph, SimpleDocTemplate,
                                Spacer, Table, TableStyle)


class NumberedCanvas(pdfcanvas.Canvas):
    """两遍绘制：第二遍才知道总页数，用于页脚「第 X 页 / 共 Y 页」"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_pages = []

    def showPage(self):
        self._saved_pages.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        total = len(self._saved_pages)
        for state in self._saved_pages:
            self.__dict__.update(state)
            self._draw_total(total)
            super().showPage()
        super().save()

    def _draw_total(self, total):
        self.saveState()
        self.setFont(_FONT, 8)
        self.setFillColor(GREY)
        self.drawRightString(PAGE_W - MARGIN_LR, FOOTER_Y,
                             f"第 {self._pageNumber} 页 / 共 {total} 页")
        self.restoreState()


# ---------- 字体 ----------
_FONT = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"
_CANDIDATES = [
    (r"C:\Windows\Fonts\msyh.ttc", 0, r"C:\Windows\Fonts\msyhbd.ttc", 0),
    (r"C:\Windows\Fonts\simsun.ttc", 0, r"C:\Windows\Fonts\simhei.ttf", None),
    (r"/usr/share/fonts/truetype/wqy/wqy-microhei.ttc", 0, None, None),
]


def _register_font():
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
    "DRAFT": "草稿", "SUBMITTED": "待派工", "ASSIGNED": "已派单", "ACCEPTED": "已接单",
    "ARRIVED": "已到场", "INSPECTING": "检查中", "IN_PROGRESS": "维修中",
    "ARCHIVING": "待归档", "ARCHIVED": "已归档", "COMPLETED": "已完成", "REJECTED": "已退回",
}
PRIORITY_CN = {"LOW": "低", "MEDIUM": "中", "HIGH": "高", "CRITICAL": "紧急"}
LEVEL_CN = {"P0": "P0 严重", "P1": "P1 重要", "P2": "P2 一般", "P3": "P3 提示"}
TYPE_CN = {"REPAIR": "报修", "MAINTENANCE": "保养", "INSPECTION": "点检", "IMPORT": "导入"}
SERVICE_CN = {"REMOTE": "远程处理", "SITE": "现场处理", "RMA": "返厂维修"}
RESULT_CN = {"PERMANENT_FIX": "彻底修复", "TEMPORARY_FIX": "临时处理", "UNABLE_FIX": "无法修复"}
SLA_CN = {"ON_TIME": "按时完成", "AT_RISK": "即将超时", "OVERDUE": "已超时"}

# ---------- 版式常量 ----------
THEME = colors.HexColor("#0FC6C2")
THEME_SOFT = colors.HexColor("#F0FBFB")
GREY = colors.HexColor("#666666")
LIGHT = colors.HexColor("#F7F9FA")
LINE = colors.HexColor("#DDE1E8")

PAGE_W, PAGE_H = A4
MARGIN_LR = 18 * mm
CONTENT_W = PAGE_W - 2 * MARGIN_LR  # 174mm

HEADER_Y = PAGE_H - 12 * mm
FOOTER_Y = 10 * mm


def _styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontName=_FONT_BOLD,
                                fontSize=18, leading=23, alignment=TA_CENTER, spaceAfter=2),
        "sub": ParagraphStyle("s", fontName=_FONT, fontSize=9.5, leading=14,
                              textColor=GREY, alignment=TA_CENTER, spaceAfter=10),
        "h": ParagraphStyle("h", fontName=_FONT_BOLD, fontSize=10.5, leading=15,
                            textColor=THEME, spaceBefore=7, spaceAfter=3),
        "body": ParagraphStyle("b", fontName=_FONT, fontSize=9.2, leading=14, spaceAfter=1),
        "cell": ParagraphStyle("c", fontName=_FONT, fontSize=9, leading=13),
        "cell_sm": ParagraphStyle("csm", fontName=_FONT, fontSize=8.5, leading=11),
        "cellb": ParagraphStyle("cb", fontName=_FONT_BOLD, fontSize=9, leading=13),
        "small": ParagraphStyle("sm", fontName=_FONT, fontSize=7.5, leading=10, textColor=GREY),
    }


def _fmt(dt):
    if not dt:
        return "—"
    if isinstance(dt, str):
        return dt[:16].replace("T", " ")
    return dt.strftime("%Y-%m-%d %H:%M")


def _section_title(text, st):
    """统一章节标题：品牌色竖条 + 标题"""
    return Paragraph(f'<font color="#0FC6C2">▍</font> {text}', st["h"])


def _grid_table(rows, col_widths, header_bg=LIGHT, compact=False):
    """统一表格样式"""
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("BACKGROUND", (0, 0), (-1, 0), header_bg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2 if compact else 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2 if compact else 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def build_work_order_pdf(wo, technician_name=None, creator_name=None, progress_logs=None,
                         device_name=None) -> bytes:
    st = _styles()
    buf = io.BytesIO()

    status_cn = SG.label_of(wo.status)  # 对外只显示 6 个业务状态
    level_cn = LEVEL_CN.get(wo.alert_level or "P2", "P2 一般")

    # ---------- 页眉/页脚 ----------
    def on_page(canvas, doc):
        canvas.saveState()
        # 页眉
        canvas.setFont(_FONT, 8)
        canvas.setFillColor(GREY)
        canvas.drawString(MARGIN_LR, HEADER_Y + 6 * mm, "芯光数智 · 设备维修管理平台")
        canvas.drawRightString(PAGE_W - MARGIN_LR, HEADER_Y + 6 * mm, f"工单 {wo.work_order_no}")
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.6)
        canvas.line(MARGIN_LR, HEADER_Y + 3.5 * mm, PAGE_W - MARGIN_LR, HEADER_Y + 3.5 * mm)
        # 页脚
        canvas.setFont(_FONT, 8)
        canvas.setFillColor(GREY)
        canvas.drawString(MARGIN_LR, FOOTER_Y,
                          f"打印时间 {datetime.now():%Y-%m-%d %H:%M}")
        # 页码由 NumberedCanvas 第二遍统一绘制（含总页数）
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN_LR, rightMargin=MARGIN_LR,
        topMargin=22 * mm, bottomMargin=18 * mm,
        title=f"设备维修工单 {wo.work_order_no}", author="芯光数智",
        subject="设备维修工单", creator="芯光数智 · 设备维修管理平台",
    )
    story = []

    # ===== 标题 =====
    story.append(Paragraph("设备维修工单", st["title"]))
    story.append(Paragraph(
        f"{wo.work_order_no}　·　{level_cn}　·　{status_cn}", st["sub"]))

    # ===== 基本信息（4 组 16 项，严格占满正文宽） =====
    def pair(label, value):
        return [Paragraph(label, st["cellb"]), Paragraph(str(value) if value not in (None, "") else "—", st["cell"])]

    left = [
        pair("工单类型", TYPE_CN.get(wo.order_type or "REPAIR", "报修")),
        pair("优先级", PRIORITY_CN.get(wo.priority or "MEDIUM", "中")),
        pair("服务器", wo.device_code or "—"),
        pair("设备名称", device_name or "—"),
        pair("GPU 序号", wo.gpu_index or "—"),
        pair("故障件SN", wo.fault_device_sn or "—"),
        pair("服务方式", SERVICE_CN.get(wo.service_mode or "", "—")),
        pair("是否返厂", "是" if wo.need_rma else ("否" if wo.need_rma is False else "—")),
    ]
    right = [
        pair("报修人", creator_name or "—"),
        pair("维修员", technician_name or "—"),
        pair("创建时间", _fmt(wo.created_at)),
        pair("完成时间", _fmt(wo.resolved_at or wo.end_time)),
        pair("响应截止", _fmt(wo.response_due_at)),
        pair("修复截止", _fmt(wo.resolve_due_at)),
        pair("SLA 状态", SLA_CN.get(wo.sla_status or "", "—")),
        pair("当前位置", wo.location or "—"),
    ]

    # 2 组/行：左标签+值、右标签+值，日期可单行
    grid = []
    for i in range(8):
        a = left[i] if i < len(left) else ["", ""]
        b = right[i] if i < len(right) else ["", ""]
        grid.append(a + b)

    # 174mm = 22 + 65 + 22 + 65
    info_w = [22 * mm, 65 * mm, 22 * mm, 65 * mm]
    info = Table(grid, colWidths=info_w)
    info.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        *[("BACKGROUND", (c, 0), (c, -1), LIGHT) for c in (0, 2)],
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(info)

    # ===== 文本段落 =====
    def section(title, text):
        if not text or not str(text).strip():
            return
        story.append(_section_title(title, st))
        story.append(Paragraph(str(text).replace("\n", "<br/>"), st["body"]))

    section("故障描述", wo.fault_description)
    section("故障现象", wo.fault_phenomenon)
    section("根本原因", wo.root_cause)
    section("解决方案", wo.solution_steps)
    section("维修结果", RESULT_CN.get(wo.repair_result or "", wo.repair_result or ""))
    section("后续计划", wo.follow_up_plan)
    section("设备日志", wo.log_text)

    # ===== 备件使用 =====
    parts = wo.used_parts or []
    if parts:
        story.append(_section_title("备件使用", st))
        rows = [[Paragraph("备件名称", st["cellb"]), Paragraph("编码", st["cellb"]),
                 Paragraph("数量", st["cellb"]), Paragraph("单价(元)", st["cellb"]),
                 Paragraph("小计(元)", st["cellb"])]]
        total = 0.0
        for p in parts:
            qty = p.get("quantity") or p.get("qty") or 0
            price = p.get("unit_price") or p.get("price") or 0
            sub = float(qty) * float(price) if isinstance(price, (int, float)) else 0
            total += sub
            rows.append([
                Paragraph(str(p.get("part_name") or p.get("name") or "—"), st["cell"]),
                Paragraph(str(p.get("part_code") or p.get("code") or "—"), st["cell"]),
                Paragraph(str(qty), st["cell"]),
                Paragraph(f"{price:,.2f}" if isinstance(price, (int, float)) else str(price), st["cell"]),
                Paragraph(f"{sub:,.2f}" if sub else "—", st["cell"]),
            ])
        rows.append([Paragraph("合计", st["cellb"]), Paragraph("", st["cell"]),
                     Paragraph("", st["cell"]), Paragraph("", st["cell"]),
                     Paragraph(f"{total:,.2f}", st["cellb"])])
        story.append(_grid_table(rows, [58 * mm, 40 * mm, 18 * mm, 29 * mm, 29 * mm]))

    # ===== 费用 =====
    story.append(_section_title("费用", st))
    cost = [[
        Paragraph(f"工时 {wo.work_hours or 0:g} 小时", st["cell"]),
        Paragraph(f"人工成本 {wo.labor_cost or 0:,.2f} 元", st["cell"]),
        Paragraph(f"备件成本 {wo.parts_cost or 0:,.2f} 元", st["cell"]),
        Paragraph(f"<b>合计 {wo.total_cost or 0:,.2f} 元</b>", st["cell"]),
    ]]
    ct = Table(cost, colWidths=[CONTENT_W / 4] * 4)
    ct.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (3, 0), (3, 0), THEME_SOFT),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.append(ct)

    # ===== 处理进度 =====
    if progress_logs:
        story.append(_section_title("处理进度", st))
        rows = [[Paragraph("时间", st["cellb"]), Paragraph("环节", st["cellb"]),
                 Paragraph("操作人", st["cellb"]), Paragraph("说明", st["cellb"])]]
        for log in progress_logs:
            to = getattr(log, "to_status", None)
            to = to.value if hasattr(to, "value") else to
            rows.append([
                Paragraph(_fmt(getattr(log, "created_at", None)), st["cell_sm"]),
                Paragraph(SG.label_of(to) if to else "—", st["cell_sm"]),
                Paragraph(getattr(log, "operator_name", None) or "—", st["cell_sm"]),
                Paragraph((getattr(log, "remark", None) or "—")[:80], st["cell_sm"]),
            ])
        story.append(_grid_table(rows, [30 * mm, 22 * mm, 28 * mm, 94 * mm], compact=True))

    # ===== 满意度 =====
    if wo.satisfaction_score:
        story.append(_section_title("报修人评价", st))
        stars = "★" * int(wo.satisfaction_score) + "☆" * (5 - int(wo.satisfaction_score))
        story.append(Paragraph(
            f"{stars}　{wo.satisfaction_score}/5　{wo.satisfaction_comment or ''}", st["body"]))

    # ===== 签字栏 =====
    story.append(Spacer(1, 4 * mm))
    sign = [[
        Paragraph("报修人签字：________________", st["cell_sm"]),
        Paragraph("维修员签字：________________", st["cell_sm"]),
        Paragraph("主管审核：________________", st["cell_sm"]),
    ]]
    sg = Table(sign, colWidths=[CONTENT_W / 3] * 3)
    sg.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story.append(KeepTogether(sg))

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page, canvasmaker=NumberedCanvas)
    return buf.getvalue()

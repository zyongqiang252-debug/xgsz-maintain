"""统一的 Excel 导出样式

所有导出接口（工单/备件/知识/流水/设备/全量）共用，保证格式一致：
- 顶部大标题（合并单元格）+ 导出时间
- 表头：品牌色底、白字加粗、居中、行高 28，冻结表头
- 数据：细边框、行高 20、斑马纹、垂直居中
- 数字列千分位/金额两位小数；长文本自动换行
- 自动筛选、列宽自适应（中文按 2 字符宽计算）
- 打印设置：A4 横向、宽度适配一页、页脚页码
"""
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ---------- 主题色 ----------
PRIMARY = "0FC6C2"
PRIMARY_LIGHT = "E8F9F9"
ZEBRA = "FAFBFC"
BORDER = "DCE1E8"
TEXT = "1D2129"
MUTED = "6B7280"

THIN = Side(style="thin", color=BORDER)
ALL_BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

HEAD_FILL = PatternFill("solid", fgColor=PRIMARY)
HEAD_FONT = Font(name="微软雅黑", bold=True, color="FFFFFF", size=10.5)
TITLE_FONT = Font(name="微软雅黑", bold=True, color=TEXT, size=15)
SUB_FONT = Font(name="微软雅黑", color=MUTED, size=9)
CELL_FONT = Font(name="微软雅黑", color=TEXT, size=10)
ZEBRA_FILL = PatternFill("solid", fgColor=ZEBRA)

CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
LEFT = Alignment(horizontal="left", vertical="center", wrap_text=False)
LEFT_WRAP = Alignment(horizontal="left", vertical="center", wrap_text=True)
RIGHT = Alignment(horizontal="right", vertical="center")

# 数字格式别名
MONEY = "#,##0.00"
INT = "#,##0"
PCT = "0.0%"


def _disp_width(value) -> int:
    """显示宽度：中文/全角算 2，其余算 1"""
    s = str(value or "")
    w = sum(2 if ord(ch) > 127 else 1 for ch in s)
    return w


def add_sheet(wb: Workbook, title: str, headers, rows,
              formats: dict = None, wrap_cols=None, widths: dict = None,
              with_title: bool = True, landscape: bool = True):
    """向工作簿添加一个规范化的 Sheet

    formats: {列名: 数字格式}，如 {"单价": MONEY}
    wrap_cols: 需要自动换行的列名集合
    widths: {列名: 固定列宽}
    """
    formats = formats or {}
    wrap_cols = set(wrap_cols or [])
    widths = widths or {}

    ws = wb.create_sheet(title=title)
    headers = list(headers)
    ncol = len(headers)

    row_idx = 1
    # ---------- 大标题 ----------
    if with_title:
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncol)
        c = ws.cell(row=1, column=1, value=title)
        c.font = TITLE_FONT
        c.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[1].height = 30

        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncol)
        c = ws.cell(row=2, column=1,
                    value=f"芯光智数 · 设备维修管理平台    导出于 {datetime.now():%Y-%m-%d %H:%M}")
        c.font = SUB_FONT
        c.alignment = Alignment(horizontal="left", vertical="center")
        ws.row_dimensions[2].height = 20
        row_idx = 3

    # ---------- 表头 ----------
    head_row = row_idx
    for i, h in enumerate(headers, start=1):
        c = ws.cell(row=head_row, column=i, value=h)
        c.fill = HEAD_FILL
        c.font = HEAD_FONT
        c.alignment = CENTER
        c.border = ALL_BORDER
    ws.row_dimensions[head_row].height = 28

    # ---------- 数据 ----------
    for r, row in enumerate(rows, start=head_row + 1):
        for i, val in enumerate(row, start=1):
            c = ws.cell(row=r, column=i, value=val)
            c.font = CELL_FONT
            c.border = ALL_BORDER
            name = headers[i - 1]
            if name in formats:
                c.number_format = formats[name]
                c.alignment = RIGHT
            elif name in wrap_cols:
                c.alignment = LEFT_WRAP
            else:
                c.alignment = LEFT
            if (r - head_row) % 2 == 0:
                c.fill = ZEBRA_FILL
        ws.row_dimensions[r].height = 20

    # ---------- 列宽 / 冻结 / 筛选 ----------
    for i, h in enumerate(headers, start=1):
        if h in widths:
            w = widths[h]
        else:
            longest = max([_disp_width(h)] + [_disp_width(row[i - 1]) for row in rows] or [8])
            w = min(48, max(9, longest + 3))
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = ws.cell(row=head_row + 1, column=1)
    if rows:
        ws.auto_filter.ref = f"A{head_row}:{get_column_letter(ncol)}{head_row + len(rows)}"

    # ---------- 打印设置 ----------
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{head_row}:{head_row}"
    ws.oddFooter.center.text = "第 &P 页 / 共 &N 页"
    ws.oddFooter.center.size = 8
    ws.oddFooter.center.color = "808080"
    return ws


def workbook_bytes(wb: Workbook) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def filename_headers(cn_name: str, ascii_name: str) -> dict:
    from urllib.parse import quote
    disp = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(cn_name)}"
    return {"Content-Disposition": disp}

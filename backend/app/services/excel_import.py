"""历史工单 Excel / CSV 台账导入

客户现场的历史工单大多是 Excel 台账，单元格字段与系统字段并不一致，
因此采用「模板 + 字段映射 + 逐行校验」的方式：

1. 上传 xlsx / csv → 读取表头 → 自动按中文别名猜映射（人工可改）
2. 逐行规范化（日期、工时、枚举、备件、标签）→ 必填校验 → 生成待确认记录
3. 走与 PDF 导入相同的人工确认流程（确认后才写入 work_orders 并收录知识库）
"""
from __future__ import annotations

import csv
import io
import re
from datetime import date, datetime, time
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger

# ============================================================
# 字段定义（label 带 * 表示必填）
# ============================================================
FIELD_DEFS: List[Dict[str, Any]] = [
    {"key": "work_order_no", "label": "工单号", "required": False,
     "aliases": ["工单号", "工单编号", "报修单号", "单号", "工单编码", "work_order_no", "wo_no"]},
    {"key": "gpu_index", "label": "故障GPU", "required": False,
     "aliases": ["故障GPU", "GPU编号", "GPU序号", "卡序号", "GPU", "gpu_index"]},
    {"key": "fault_device_sn", "label": "故障件SN", "required": False,
     "aliases": ["故障件SN", "卡SN", "GPU SN", "部件序列号", "fault_device_sn"]},
    {"key": "service_mode", "label": "服务方式", "required": False,
     "aliases": ["服务方式", "处理方式", "服务类型", "远程/现场/返厂", "service_mode"]},
    {"key": "need_rma", "label": "是否返厂", "required": False,
     "aliases": ["是否返厂", "返厂", "RMA", "需返厂", "need_rma"]},
    {"key": "device_code", "label": "设备编码", "required": False,
     "aliases": ["设备编码", "设备编号", "设备代码", "设备号", "资产编号",
                 "服务器编号", "服务器SN", "整机SN", "SN", "主机名", "机器名", "device_code"]},
    {"key": "device_name", "label": "设备名称", "required": False,
     "aliases": ["设备名称", "设备名", "服务器名称", "节点名称", "device_name"]},
    {"key": "fault_code", "label": "故障码", "required": False,
     "aliases": ["故障码", "故障代码", "故障编号", "错误码", "报警码",
                 "Xid", "XID", "xid", "fault_code"]},
    {"key": "fault_description", "label": "故障描述*", "required": True,
     "aliases": ["故障描述", "故障内容", "问题描述", "故障现象描述", "报修内容", "异常描述", "fault_description"]},
    {"key": "fault_phenomenon", "label": "故障现象", "required": False,
     "aliases": ["故障现象", "现象", "具体表现", "fault_phenomenon"]},
    {"key": "fault_category", "label": "故障大类", "required": False,
     "aliases": ["故障大类", "故障类型", "故障类别", "fault_category"]},
    {"key": "root_cause_category", "label": "根因大类", "required": False,
     "aliases": ["根因大类", "根本原因分类", "原因分类", "root_cause_category"]},
    {"key": "root_cause", "label": "根本原因", "required": False,
     "aliases": ["根本原因", "原因分析", "故障原因", "原因", "root_cause"]},
    {"key": "solution_steps", "label": "解决步骤", "required": False,
     "aliases": ["解决步骤", "维修步骤", "处理措施", "处理方法", "解决方案", "维修过程", "solution_steps"]},
    {"key": "repair_result", "label": "维修结果", "required": False,
     "aliases": ["维修结果", "处理结果", "修复结果", "repair_result"]},
    {"key": "work_hours", "label": "工时(小时)", "required": False,
     "aliases": ["工时", "维修工时", "耗时", "小时数", "work_hours"]},
    {"key": "priority", "label": "优先级", "required": False,
     "aliases": ["优先级", "紧急程度", "priority"]},
    {"key": "location", "label": "设备位置", "required": False,
     "aliases": ["设备位置", "位置", "安装位置", "机房", "机柜", "机柜号", "U位", "location"]},
    {"key": "start_time", "label": "报修时间", "required": False,
     "aliases": ["报修时间", "开始时间", "报修日期", "发生时间", "start_time"]},
    {"key": "end_time", "label": "完工时间", "required": False,
     "aliases": ["完工时间", "结束时间", "完成时间", "end_time"]},
    {"key": "reporter_name", "label": "报修人", "required": False,
     "aliases": ["报修人", "报修人姓名", "提交人", "reporter", "reporter_name"]},
    {"key": "technician_name", "label": "维修人", "required": False,
     "aliases": ["维修人", "维修员", "处理人", "负责人", "technician", "technician_name"]},
    {"key": "used_parts", "label": "更换备件", "required": False,
     "aliases": ["更换备件", "备件", "使用备件", "更换配件", "used_parts"]},
    {"key": "tags", "label": "标签", "required": False,
     "aliases": ["标签", "关键词", "tags"]},
]

FIELD_KEYS = [f["key"] for f in FIELD_DEFS]
REQUIRED_KEYS = [f["key"] for f in FIELD_DEFS if f["required"]]
MAX_ROWS = 2000


# ============================================================
# 读取表格
# ============================================================
def _cell_to_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d %H:%M") if (v.hour or v.minute) else v.strftime("%Y-%m-%d")
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d")
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()


def _xls_cell_to_text(book: Any, cell: Any) -> str:
    """把 xlrd 单元格转成文本：日期按 xldate 还原，整数去掉 .0，错误值当空"""
    import xlrd

    ctype, value = cell.ctype, cell.value
    if ctype in (xlrd.XL_CELL_EMPTY, xlrd.XL_CELL_BLANK, xlrd.XL_CELL_ERROR):
        return ""
    if ctype == xlrd.XL_CELL_DATE:
        try:
            return _cell_to_text(xlrd.xldate_as_datetime(value, book.datemode))
        except Exception:
            return _cell_to_text(value)
    if ctype == xlrd.XL_CELL_BOOLEAN:
        return "是" if value else "否"
    return _cell_to_text(value)


def read_table(path: str) -> Tuple[List[str], List[List[str]]]:
    """读取 xlsx / xls / csv，返回 (表头, 数据行)；自动跳过标题行与空行"""
    ext = path.rsplit(".", 1)[-1].lower()
    if ext in ("xlsx", "xlsm"):
        import openpyxl
        wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
        ws = wb.worksheets[0]
        raw = [[_cell_to_text(c) for c in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
    elif ext == "csv":
        text = None
        for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk"):
            try:
                with open(path, "r", encoding=enc, newline="") as fp:
                    text = fp.read()
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("CSV 编码无法识别，请另存为 UTF-8 或 GBK")
        raw = [row for row in csv.reader(io.StringIO(text))]
    elif ext == "xls":
        # 旧版 BIFF 格式（Excel 2003 及更早），openpyxl 读不了，用 xlrd
        try:
            import xlrd
        except ImportError:
            raise ValueError("解析 .xls 需要 xlrd 库：pip install xlrd，或把文件另存为 .xlsx 再导入")
        book = xlrd.open_workbook(path, on_demand=True)
        try:
            sheet = book.sheet_by_index(0)
            raw = [
                [_xls_cell_to_text(book, sheet.cell(r, c)) for c in range(sheet.ncols)]
                for r in range(sheet.nrows)
            ]
        finally:
            book.release_resources()
    else:
        raise ValueError(f"不支持的文件类型：.{ext}")

    # 丢掉全空行
    rows = [r for r in raw if any((c or "").strip() for c in r)]
    if not rows:
        raise ValueError("表格内容为空")

    # 表头行：前 5 行里非空单元格最多的那行
    header_idx, best = 0, -1
    for i, r in enumerate(rows[:5]):
        score = sum(1 for c in r if (c or "").strip())
        if score > best:
            header_idx, best = i, score

    headers = [(c or "").strip() for c in rows[header_idx]]
    # 去掉表头尾部空列
    while headers and not headers[-1]:
        headers.pop()

    data_rows = rows[header_idx + 1:]
    out: List[List[str]] = []
    for r in data_rows:
        r = (r + [""] * len(headers))[:len(headers)]
        out.append([(c or "").strip() for c in r])
    return headers, out[:MAX_ROWS]


# ============================================================
# 字段映射
# ============================================================
def _norm_header(h: str) -> str:
    return re.sub(r"[\s()（）:：*＊、/]", "", (h or "").lower())


def header_signature(headers: List[str]) -> str:
    """表头签名：规范化后排序拼接。

    排序 + 去重意味着「列顺序变了」「多了重复列」仍命中同一份映射模板；
    规范化会去掉空格/括号/冒号等噪音，避免「工单号 (必填)」和「工单号」被当成两套表头。
    """
    norm = sorted({_norm_header(h) for h in headers if (h or "").strip()})
    return "|".join(norm)[:480]


def suggest_mapping(headers: List[str]) -> Dict[str, str]:
    """按中文别名猜测映射：{系统字段: 表格列名}"""
    normalized = {_norm_header(h): h for h in headers if h}
    mapping: Dict[str, str] = {}
    used = set()
    for f in FIELD_DEFS:
        for alias in f["aliases"]:
            key = _norm_header(alias)
            if key in normalized and normalized[key] not in used:
                mapping[f["key"]] = normalized[key]
                used.add(normalized[key])
                break
    # 兜底：完全同名
    for f in FIELD_DEFS:
        if f["key"] in mapping:
            continue
        for h in headers:
            if _norm_header(h) == _norm_header(f["key"]) and h not in used:
                mapping[f["key"]] = h
                used.add(h)
                break
    # 再兜底：包含式匹配（如「工时(小时)」「维修工时(h)」）
    for f in FIELD_DEFS:
        if f["key"] in mapping:
            continue
        for alias in f["aliases"]:
            a = _norm_header(alias)
            if len(a) < 2:
                continue
            hit = next((h for h in headers if h not in used and a in _norm_header(h)), None)
            if hit:
                mapping[f["key"]] = hit
                used.add(hit)
                break
    return mapping


def resolve_mapping(headers: List[str], user_mapping: Optional[Dict[str, str]]) -> Dict[str, int]:
    """把 {字段: 列名} 转成 {字段: 列下标}，忽略不存在的列"""
    result: Dict[str, int] = {}
    header_index = {}
    for i, h in enumerate(headers):
        header_index.setdefault(h, i)
        header_index.setdefault(_norm_header(h), i)
    for key, col in (user_mapping or {}).items():
        if key not in FIELD_KEYS or not col:
            continue
        idx = header_index.get(col)
        if idx is None:
            idx = header_index.get(_norm_header(str(col)))
        if idx is not None:
            result[key] = idx
    return result


# ============================================================
# 值规范化
# ============================================================
_REPAIR_RESULT_MAP = {
    "PERMANENT_FIX": "PERMANENT_FIX", "彻底修复": "PERMANENT_FIX", "永久修复": "PERMANENT_FIX",
    "已修复": "PERMANENT_FIX", "彻底解决": "PERMANENT_FIX", "修复": "PERMANENT_FIX",
    "TEMPORARY_FIX": "TEMPORARY_FIX", "临时处理": "TEMPORARY_FIX", "临时修复": "TEMPORARY_FIX",
    "临时解决": "TEMPORARY_FIX", "临时": "TEMPORARY_FIX",
    "UNABLE_FIX": "UNABLE_FIX", "无法修复": "UNABLE_FIX", "未修复": "UNABLE_FIX",
    "无法解决": "UNABLE_FIX", "报废": "UNABLE_FIX",
}

_PRIORITY_MAP = {
    "LOW": "LOW", "低": "LOW", "较低": "LOW", "一般": "MEDIUM", "普通": "MEDIUM",
    "MEDIUM": "MEDIUM", "中": "MEDIUM", "中等": "MEDIUM",
    "HIGH": "HIGH", "高": "HIGH", "较高": "HIGH", "重要": "HIGH",
    "CRITICAL": "CRITICAL", "紧急": "CRITICAL", "严重": "CRITICAL", "特急": "CRITICAL", "致命": "CRITICAL",
}

_DT_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
    "%Y年%m月%d日 %H:%M", "%Y年%m月%d日",
    "%Y.%m.%d", "%Y%m%d",
)


def normalize_datetime(value: str) -> Optional[str]:
    s = (value or "").strip()
    if not s:
        return None
    # Excel 序列日期（纯数字）
    if re.fullmatch(r"\d{5}(\.\d+)?", s):
        try:
            from datetime import timedelta
            base = datetime(1899, 12, 30)
            dt = base + timedelta(days=float(s))
            return dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            return None
    s = s.replace("T", " ").strip()
    for fmt in _DT_FORMATS:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue
    # 只写了 3/5 这样的月日，无法判断年份，忽略
    return None


def normalize_hours(value: str) -> Tuple[Optional[float], Optional[str]]:
    s = (value or "").strip()
    if not s:
        return None, None
    m = re.search(r"-?\d+(\.\d+)?", s)
    if not m:
        return None, f"工时「{s}」无法识别为数字"
    try:
        v = float(m.group(0))
    except ValueError:
        return None, f"工时「{s}」无法识别为数字"
    if v < 0:
        return None, f"工时为负数（{v}）"
    if v > 1000:
        return None, f"工时不合理（{v}）"
    return v, None


def normalize_parts(value: str) -> List[Dict[str, Any]]:
    s = (value or "").strip()
    if not s:
        return []
    parts: List[Dict[str, Any]] = []
    for seg in re.split(r"[,，;；、\n]", s):
        seg = seg.strip()
        if not seg:
            continue
        m = re.match(r"(.+?)\s*[x×*]\s*(\d+)$", seg) or re.match(r"(.+?)\s*(\d+)\s*(?:个|件|只|套|根|米)$", seg)
        if m:
            parts.append({"name": m.group(1).strip(), "count": int(m.group(2))})
        else:
            parts.append({"name": seg, "count": 1})
    return parts


def normalize_tags(value: str) -> List[str]:
    s = (value or "").strip()
    if not s:
        return []
    return [t.strip().lstrip("#") for t in re.split(r"[,，;；、/\s]+", s) if t.strip()][:10]


# ============================================================
# 行 → 工单字段
# ============================================================
def build_row_data(values: List[str], mapping: Dict[str, int]) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """返回 (字段 dict, 警告, 错误)"""
    data: Dict[str, Any] = {}
    warnings: List[str] = []
    errors: List[str] = []

    def get(key: str) -> str:
        idx = mapping.get(key)
        if idx is None or idx >= len(values):
            return ""
        return (values[idx] or "").strip()

    for key in ("work_order_no", "device_code", "device_name", "fault_code", "fault_description",
                "fault_phenomenon", "fault_category", "root_cause_category", "root_cause",
                "solution_steps", "location", "reporter_name", "technician_name"):
        v = get(key)
        if v:
            data[key] = v

    # 必填：故障描述。现场台账常只有「故障现象」列，允许用它兜底
    if not data.get("fault_description"):
        if data.get("fault_phenomenon"):
            data["fault_description"] = data["fault_phenomenon"]
            warnings.append("故障描述取自「故障现象」列")
        elif data.get("root_cause"):
            data["fault_description"] = data["root_cause"]
            warnings.append("故障描述取自「根本原因」列")
        else:
            errors.append("缺少故障描述（必填）")

    # 枚举
    rr = get("repair_result")
    if rr:
        mapped = _REPAIR_RESULT_MAP.get(rr) or _REPAIR_RESULT_MAP.get(rr.upper())
        if mapped:
            data["repair_result"] = mapped
        else:
            warnings.append(f"维修结果「{rr}」无法识别，已留空")

    pr = get("priority")
    if pr:
        mapped = _PRIORITY_MAP.get(pr) or _PRIORITY_MAP.get(pr.upper())
        if mapped:
            data["priority"] = mapped
        else:
            warnings.append(f"优先级「{pr}」无法识别，按中等处理")

    # 工时：负数/超范围视为阻断性错误（否则会悄悄丢数据）
    hours, err = normalize_hours(get("work_hours"))
    if err:
        errors.append(err)
    if hours is not None:
        data["work_hours"] = hours

    # 文本长度护栏：库字段是 Text，但超长描述没有业务意义且会拖慢检索
    desc = data.get("fault_description") or ""
    if len(desc) > 4000:
        errors.append(f"故障描述过长（{len(desc)} 字，上限 4000）")
    elif len(desc) > 1000:
        warnings.append(f"故障描述较长（{len(desc)} 字），建议精简到 1000 字以内")

    wo_no = data.get("work_order_no") or ""
    if len(wo_no) > 50:
        errors.append(f"工单号过长（{len(wo_no)} 字，上限 50）")

    # 时间
    for key, label in (("start_time", "报修时间"), ("end_time", "完工时间")):
        raw = get(key)
        if raw:
            dt = normalize_datetime(raw)
            if dt:
                data[key] = dt
            else:
                warnings.append(f"{label}「{raw}」格式无法识别（建议 YYYY-MM-DD HH:MM）")

    # 备件 / 标签
    parts = normalize_parts(get("used_parts"))
    if parts:
        data["used_parts"] = parts
    tags = normalize_tags(get("tags"))
    if tags:
        data["tags"] = tags

    return data, warnings, errors


def parse_sheet(
    headers: List[str],
    rows: List[List[str]],
    mapping: Dict[str, int],
) -> List[Dict[str, Any]]:
    """逐行解析 + 字段级校验，返回每行结果（尚未做设备/用户匹配）"""
    results: List[Dict[str, Any]] = []
    for i, values in enumerate(rows):
        row_no = i + 1  # 相对数据区的行号（不含表头）
        if not any(values):
            continue
        data, warnings, errors = build_row_data(values, mapping)
        results.append({
            "row_no": row_no,
            "data": data,
            "warnings": warnings,
            "errors": errors,
            "raw": values,
        })
    return results


# ============================================================
# 模板生成
# ============================================================
def build_template_xlsx() -> bytes:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "工单台账"

    header_fill = PatternFill("solid", fgColor="0FC6C2")
    required_fill = PatternFill("solid", fgColor="FFE58F")
    headers = [f["label"] for f in FIELD_DEFS]
    for col, h in enumerate(headers, start=1):
        c = ws.cell(row=1, column=col, value=h)
        c.font = Font(bold=True, color="FFFFFF")
        c.fill = required_fill if h.endswith("*") else header_fill
        c.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[c.column_letter].width = max(12, min(28, len(h) * 3 + 8))
    ws.freeze_panes = "A2"

    sample = {
        "work_order_no": "WO-2026-0001",
        "gpu_index": "GPU3",
        "fault_device_sn": "SN-H100-GPU3-0007",
        "service_mode": "返厂维修",
        "need_rma": "是",
        "device_code": "GPU-SRV-001",
        "device_name": "计算集群 01 号节点",
        "fault_code": "XID-79",
        "fault_description": "训练任务报 CUDA error，nvidia-smi 中 GPU3 消失",
        "fault_phenomenon": "dmesg 出现 NVRM: Xid 79, GPU has fallen off the bus",
        "fault_category": "GPU硬件故障",
        "root_cause_category": "硬件老化/损坏",
        "root_cause": "显存坏块导致 GPU 掉卡",
        "solution_steps": "1.复位 GPU；2.检查供电与散热；3.仍复现则更换 GPU 卡；4.gpu-burn 验证",
        "repair_result": "彻底修复",
        "work_hours": "4.5",
        "priority": "高",
        "location": "机房A / 机柜A03 / U12-U19",
        "start_time": "2026-03-05 09:30",
        "end_time": "2026-03-05 14:00",
        "reporter_name": "张三",
        "technician_name": "李四",
        "used_parts": "GPU-H100-80Gx1",
        "tags": "Xid79,掉卡",
    }
    for col, f in enumerate(FIELD_DEFS, start=1):
        ws.cell(row=2, column=col, value=sample.get(f["key"], ""))

    # 说明页
    ws2 = wb.create_sheet("填写说明")
    ws2.column_dimensions["A"].width = 18
    ws2.column_dimensions["B"].width = 14
    ws2.column_dimensions["C"].width = 70
    ws2.append(["字段", "是否必填", "说明"])
    for c in ws2[1]:
        c.font = Font(bold=True)
        c.fill = header_fill
        c.font = Font(bold=True, color="FFFFFF")
    notes = {
        "work_order_no": "留空则系统自动生成 WO-日期-序号",
        "device_code": "需与设备台账中的编码一致，否则确认时会提示未匹配",
        "fault_description": "必填，简洁概括故障内容",
        "repair_result": "可填：彻底修复 / 临时处理 / 无法修复",
        "work_hours": "数字，单位小时，可写 4.5 或 4.5小时",
        "priority": "可填：低 / 一般 / 高 / 紧急",
        "start_time": "建议格式 2024-03-05 09:30，也支持 2024/3/5",
        "end_time": "同上",
        "technician_name": "需与系统用户姓名一致，否则不自动关联维修人",
        "reporter_name": "需与系统用户姓名一致",
        "used_parts": "多个备件用逗号分隔，可写 轴承x2, 密封圈x1",
        "tags": "多个标签用逗号或空格分隔",
    }
    for f in FIELD_DEFS:
        ws2.append([f["label"], "是" if f["required"] else "否", notes.get(f["key"], "")])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()

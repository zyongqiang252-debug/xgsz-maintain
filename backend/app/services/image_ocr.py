"""历史工单图片（纸质工单拍照 / 扫描件）OCR 导入

链路：
    图片 → RapidOCR 本地识别出文字（离线，不需要外网与大模型）
         → 结构化：配置了模型 Key 时走 LLM 抽取；否则走本地规则提取
         → 校验 → 写入待确认记录，人工核对后再入库

设计原则：OCR 结果一定不完美，所以宁可少提字段，也不编造；
所有由图片导入的记录都带「请人工核对原文」提示。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

from loguru import logger

_OCR = None


def _get_ocr():
    """懒加载 RapidOCR 单例（模型首次加载约 1-2 秒）"""
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR
        _OCR = RapidOCR()
    return _OCR


def ocr_image(path: str) -> str:
    """对单张图片做 OCR，按行返回文本"""
    ocr = _get_ocr()
    result, _ = ocr(path)
    if not result:
        return ""
    # result: [[box, text, score], ...]，按 y 坐标排序还原阅读顺序
    lines = sorted(result, key=lambda r: (min(p[1] for p in r[0]), min(p[0] for p in r[0])))
    return "\n".join(str(r[1]).strip() for r in lines if str(r[1]).strip())


# ============================================================
# 规则提取（无模型 Key 时的兜底）
# ============================================================
_DATE_RE = r"(20\d{2}[-/年.]\d{1,2}[-/月.]\d{1,2}[日]?(?:\s*\d{1,2}[:：]\d{2})?)"


def _find(pattern: str, text: str, group: int = 1) -> str:
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        return ""
    try:
        return (m.group(group) or "").strip(" ：:，,。;；")
    except IndexError:
        return ""


def _section(text: str, titles: List[str], max_len: int = 300) -> str:
    """取「标题：内容」这种行的内容；标题后无内容时取下一行"""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        for t in titles:
            if t in line:
                after = re.split(r"[:：]", line, maxsplit=1)
                if len(after) == 2 and after[1].strip():
                    return after[1].strip()[:max_len]
                if i + 1 < len(lines):
                    nxt = lines[i + 1].strip()
                    if nxt and len(nxt) >= 4:
                        return nxt[:max_len]
    return ""


def rule_extract(text: str) -> Tuple[Dict, List[str]]:
    """不依赖大模型的结构化提取：只提格式稳定、可信度高的字段"""
    data: Dict = {}
    warnings: List[str] = []

    # 工单号：优先带标签，其次宽松匹配 WO- 前缀
    wo_no = _find(r"(?:工单号|工单编号|报修单号|单\s*号)\s*[:：]?\s*([A-Za-z]{1,4}[-_]?\d{2,}[-_]?[A-Za-z0-9]{0,10})", text)
    if not wo_no:
        m = re.search(r"\b(WO[-_]?\d{4,}(?:[-_]\d+)?)\b", text)
        wo_no = m.group(1) if m else ""
    if wo_no:
        wo_no = wo_no.replace("0-", "O-") if re.match(r"W0", wo_no) else wo_no
        data["work_order_no"] = wo_no.upper()

    device_code = _find(r"(?:设备编码|设备编号|设备代码|设备号|资产编号)\s*[:：]?\s*([A-Za-z0-9][A-Za-z0-9\-_/]{2,30})", text)
    if device_code:
        data["device_code"] = device_code

    device_name = _find(r"(?:设备名称|设备名)\s*[:：]?\s*([\u4e00-\u9fa5A-Za-z0-9（）()\-]{2,30})", text)
    if device_name:
        data["device_name"] = device_name

    fault_code = _find(r"(?:故障码|故障代码|故障编号)\s*[:：]?\s*(\d{4,8}(?:\s*[,，]\s*\d{4,8})*)", text)
    if fault_code:
        data["fault_code"] = re.sub(r"\s+", "", fault_code)

    # 故障描述：优先标签，其次找含故障关键词的行
    desc = _section(text, ["故障描述", "故障内容", "问题描述", "报修内容"])
    if not desc:
        for line in text.splitlines():
            if any(k in line for k in ("异响", "漏油", "报警", "振纹", "过热", "停机", "不启动", "故障")):
                if len(line) >= 6:
                    desc = line.strip()[:300]
                    break
    if desc:
        data["fault_description"] = desc

    phenomenon = _section(text, ["故障现象", "现象描述"])
    if phenomenon:
        data["fault_phenomenon"] = phenomenon

    root_cause = _section(text, ["根本原因", "原因分析", "故障原因"])
    if root_cause:
        data["root_cause"] = root_cause

    steps = _section(text, ["解决步骤", "维修步骤", "处理措施", "处理方法", "解决方案"], max_len=600)
    if steps:
        data["solution_steps"] = steps

    hours = _find(r"(?:工时|耗时|维修工时)\s*[:：]?\s*(\d+(?:\.\d+)?)", text)
    if hours:
        data["work_hours"] = float(hours)

    tech = _find(r"(?:维修人|维修员|处理人|维修人员)\s*[:：]?\s*([\u4e00-\u9fa5]{2,6})", text)
    if tech:
        data["technician_name"] = tech

    reporter = _find(r"(?:报修人|报修人员|申请人|提交人)\s*[:：]?\s*([\u4e00-\u9fa5]{2,6})", text)
    if reporter:
        data["reporter_name"] = reporter

    start = _find(r"(?:报修时间|报修日期|开始时间|发生时间)\s*[:：]?\s*" + _DATE_RE, text)
    if start:
        data["start_time"] = start.replace("年", "-").replace("月", "-").replace("日", "")
    end = _find(r"(?:完工时间|完成时间|结束时间)\s*[:：]?\s*" + _DATE_RE, text)
    if end:
        data["end_time"] = end.replace("年", "-").replace("月", "-").replace("日", "")

    location = _find(r"(?:设备位置|安装位置|位置)\s*[:：]?\s*([\u4e00-\u9fa5A-Za-z0-9\-号栋楼层区车间]{2,40})", text)
    if location:
        data["location"] = location

    if not data.get("fault_description"):
        warnings.append("未识别到故障描述，请人工补充（必填）")
    warnings.append("图片 OCR 结果仅供参考，请逐项核对原文后再入库")
    return data, warnings


def structure_text(text: str) -> Tuple[Dict, List[str]]:
    """优先用大模型结构化，未配置 Key 或调用失败时回退到规则提取"""
    from app.core.config import settings

    if settings.DEEPSEEK_API_KEY:
        try:
            from app.agents.work_order_importer import _extract_work_order
            data = _extract_work_order(text)
            if data:
                return data, ["图片 OCR + 大模型抽取结果，请核对原文后再入库"]
        except Exception as e:
            logger.warning(f"[ImageImport] 大模型抽取失败，回退规则提取: {e}")
    return rule_extract(text)

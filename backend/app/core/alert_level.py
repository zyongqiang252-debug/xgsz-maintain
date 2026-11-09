"""统一告警级别 P0/P1/P2/P3

全系统共用一套级别：设备告警、站内通知、工单优先级、库存预警都映射到这里，
前端只认 P0~P3，颜色与排序由后端给出，避免各模块各写一套。

- P0 严重：业务中断 / 硬件损坏 / 需立即处理（掉卡、Xid 79、UCE、缺货）
- P1 重要：影响性能或存在风险（温度高、降频、低库存、SLA 超时）
- P2 一般：需要关注但不紧急（单次告警、例行提醒）
- P3 提示：信息类（系统提示、操作成功）
"""
from typing import Optional

P0 = "P0"
P1 = "P1"
P2 = "P2"
P3 = "P3"

LEVELS = {
    P0: {"label": "严重", "color": "#F53F3F", "type": "danger", "order": 0},
    P1: {"label": "重要", "color": "#FF7D00", "type": "warning", "order": 1},
    P2: {"label": "一般", "color": "#FFC53D", "type": "warning", "order": 2},
    P3: {"label": "提示", "color": "#86909C", "type": "info", "order": 3},
}

# 旧值 / 英文值 -> 统一级别
_ALIASES = {
    "P0": P0, "P1": P1, "P2": P2, "P3": P3,
    "CRITICAL": P0, "FATAL": P0, "严重": P0, "紧急": P0,
    "ERROR": P1, "HIGH": P1, "重要": P1, "高": P1,
    "WARNING": P2, "WARN": P2, "MEDIUM": P2, "一般": P2, "中": P2, "警告": P2,
    "INFO": P3, "LOW": P3, "提示": P3, "低": P3, "信息": P3,
}

# 工单优先级 -> 告警级别
_PRIORITY_MAP = {
    "CRITICAL": P0, "HIGH": P1, "MEDIUM": P2, "LOW": P3,
}


def normalize(value: Optional[str], default: str = P2) -> str:
    """任意旧值归一成 P0~P3"""
    if not value:
        return default
    return _ALIASES.get(str(value).strip().upper(), _ALIASES.get(str(value).strip(), default))


def from_priority(priority: Optional[str]) -> str:
    """工单优先级转告警级别"""
    if not priority:
        return P2
    return _PRIORITY_MAP.get(str(priority).strip().upper(), P2)


def order_of(level: Optional[str]) -> int:
    return LEVELS.get(normalize(level), LEVELS[P2])["order"]


def label_of(level: Optional[str]) -> str:
    return LEVELS.get(normalize(level), LEVELS[P2])["label"]


def highest(levels) -> Optional[str]:
    """一组级别里最高的（P0 最高）"""
    best = None
    best_order = 99
    for lv in levels or []:
        lv = normalize(lv, default="")
        if not lv:
            continue
        o = LEVELS.get(lv, LEVELS[P2])["order"]
        if o < best_order:
            best_order = o
            best = lv
    return best


def as_dict() -> dict:
    """给前端下拉/图例用"""
    return {k: dict(v, value=k) for k, v in LEVELS.items()}

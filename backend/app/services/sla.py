"""SLA（响应/修复时限）与回访、成本核算

规则（可在 .env 覆盖）：
- 响应时限：从建单到"接单(ACCEPTED)"
- 修复时限：从建单到"完成(COMPLETED)"
- 按优先级给不同小时数，默认 CRITICAL 2h/8h、HIGH 4h/24h、MEDIUM 8h/48h、LOW 24h/72h
- sla_status：ON_TIME / AT_RISK（剩余 <20%）/ OVERDUE
"""
from datetime import datetime, timedelta
from typing import Optional, Tuple

from app.core.config import settings

DEFAULT_SLA = {
    "CRITICAL": (2, 8),
    "HIGH": (4, 24),
    "MEDIUM": (8, 48),
    "LOW": (24, 72),
}


def _hours(priority: str) -> Tuple[float, float]:
    p = (priority or "MEDIUM").upper()
    base = DEFAULT_SLA.get(p, DEFAULT_SLA["MEDIUM"])
    resp = getattr(settings, f"SLA_RESPONSE_HOURS_{p}", None)
    resv = getattr(settings, f"SLA_RESOLVE_HOURS_{p}", None)
    return (float(resp) if resp is not None else base[0],
            float(resv) if resv is not None else base[1])


def compute_due(priority: str, created_at: Optional[datetime] = None) -> Tuple[datetime, datetime]:
    """返回 (响应截止, 修复截止)"""
    base = created_at or datetime.now()
    resp_h, resv_h = _hours(priority)
    return base + timedelta(hours=resp_h), base + timedelta(hours=resv_h)


def evaluate(wo) -> dict:
    """评估单张工单的 SLA 状态（不落库，供接口返回）"""
    now = datetime.now()
    resp_due = getattr(wo, "response_due_at", None)
    resv_due = getattr(wo, "resolve_due_at", None)
    status = getattr(wo, "status", None)
    status_val = status.value if hasattr(status, "value") else str(status or "")

    if status_val in ("COMPLETED", "ARCHIVED"):
        done = getattr(wo, "resolved_at", None) or getattr(wo, "updated_at", None)
        overdue = bool(resv_due and done and done > resv_due)
        return {
            "sla_status": "OVERDUE" if overdue else "ON_TIME",
            "response_due_at": resp_due.isoformat() if resp_due else None,
            "resolve_due_at": resv_due.isoformat() if resv_due else None,
            "resolve_remaining_minutes": None,
            "overdue": overdue,
        }

    first = getattr(wo, "first_response_at", None)
    resp_overdue = bool(resp_due and not first and now > resp_due)
    resv_remaining = None
    resv_overdue = False
    at_risk = False
    if resv_due:
        resv_remaining = int((resv_due - now).total_seconds() // 60)
        resv_overdue = resv_remaining < 0
        total = max(1, int((resv_due - (getattr(wo, "created_at", None) or now)).total_seconds() // 60))
        at_risk = (not resv_overdue) and resv_remaining < max(30, total * 0.2)

    if resp_overdue or resv_overdue:
        sla = "OVERDUE"
    elif at_risk:
        sla = "AT_RISK"
    else:
        sla = "ON_TIME"
    return {
        "sla_status": sla,
        "response_due_at": resp_due.isoformat() if resp_due else None,
        "resolve_due_at": resv_due.isoformat() if resv_due else None,
        "resolve_remaining_minutes": resv_remaining,
        "overdue": sla == "OVERDUE",
    }


def mark_overdue(wo) -> None:
    """落库 sla_status（列表筛选/progress 用）"""
    info = evaluate(wo)
    wo.sla_status = info["sla_status"]


def recompute_cost(wo, db=None) -> dict:
    """重算人工/备件/总成本

    - 人工 = work_hours × HOURLY_LABOR_RATE
    - 备件 = used_parts 里每项按 part_code 查单价 × 数量（查不到用 0）
    """
    rate = float(getattr(settings, "HOURLY_LABOR_RATE", 80.0))
    hours = float(getattr(wo, "work_hours", 0) or 0)
    labor = round(hours * rate, 2)

    parts_cost = 0.0
    for item in (getattr(wo, "used_parts", None) or []):
        if not isinstance(item, dict):
            continue
        qty = float(item.get("count") or item.get("qty") or 0)
        price = item.get("unit_price")
        if price is None and db is not None and item.get("code"):
            try:
                from app.models.spare_part import SparePart
                sp = db.query(SparePart).filter(SparePart.part_code == item["code"]).first()
                price = (sp.unit_price or 0) if sp else 0
            except Exception:
                price = 0
        parts_cost += float(price or 0) * qty
    parts_cost = round(parts_cost, 2)

    wo.labor_cost = labor
    wo.parts_cost = parts_cost
    wo.total_cost = round(labor + parts_cost, 2)
    return {"labor_cost": labor, "parts_cost": parts_cost, "total_cost": wo.total_cost}

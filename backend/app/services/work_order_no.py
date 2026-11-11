"""工单编号统一生成：xgsz-YYYYMMDD-NNN（每天从 001 开始）。"""
from datetime import date

from sqlalchemy.orm import Session

from app.models.work_order import WorkOrder


def next_work_order_no(db: Session, day: date | None = None) -> str:
    day = day or date.today()
    prefix = f"xgsz-{day:%Y%m%d}-"
    latest = (db.query(WorkOrder)
              .filter(WorkOrder.work_order_no.like(f"{prefix}%"))
              .order_by(WorkOrder.work_order_no.desc())
              .first())
    seq = 1
    if latest and latest.work_order_no:
        try:
            seq = int(latest.work_order_no.split("-")[-1]) + 1
        except ValueError:
            seq = 1
    return f"{prefix}{seq:03d}"

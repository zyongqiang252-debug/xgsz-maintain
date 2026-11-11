# -*- coding: utf-8 -*-
"""APScheduler 周期性任务

目前两个：
1. ``run_stock_alert_check``  每小时检查库存预警（站内通知 6 小时去重，群推送在出库瞬间就发过了）
2. ``run_maintenance_due_check`` 每天扫描保养计划，到期前 3 天提醒负责人（同一计划 24 小时内只提醒一次）

两者都自己开数据库会话、自己 try/except，失败只记日志，不能影响主服务。
"""
from datetime import datetime, timedelta

from loguru import logger


def run_stock_alert_check() -> dict:
    """库存预警巡检（原来 stock_alert.run_periodic_check 写了但没人调用，现在挂到 APScheduler）"""
    try:
        from app.core.stock_alert import check_and_notify_stock_alerts
        result = check_and_notify_stock_alerts()
        if result.get("alert_count"):
            logger.warning(f"[Jobs][StockAlert] 预警 {result['alert_count']} 项")
        return result or {}
    except Exception as e:
        logger.exception(f"[Jobs][StockAlert] 巡检失败: {e}")
        return {}


def run_maintenance_due_check(days_ahead: int = 3) -> int:
    """保养计划到期提醒：到期前 N 天通知负责人；没有负责人的通知管理员/主管"""
    from app.core.database import SessionLocal  # 延迟导入，避免模块级循环

    db = SessionLocal()
    try:
        from app.api.notifications import notify_roles, notify_user
        from app.models.maintenance import MaintenancePlan
        from app.models.notification import Notification

        now = datetime.now()
        cutoff = now + timedelta(days=days_ahead)
        plans = (db.query(MaintenancePlan)
                 .filter(MaintenancePlan.status == "ACTIVE",
                         MaintenancePlan.next_due_at.isnot(None),
                         MaintenancePlan.next_due_at <= cutoff)
                 .all())
        sent = 0
        for plan in plans:
            marker = f"计划#{plan.id} "
            recent = (db.query(Notification)
                      .filter(Notification.type == "MAINTENANCE",
                              Notification.content.like(f"%{marker}%"),
                              Notification.created_at >= now - timedelta(hours=24))
                      .first())
            if recent:
                continue
            due = plan.next_due_at.strftime("%Y-%m-%d") if plan.next_due_at else "-"
            content = (f"{marker}{plan.plan_name}（设备 {plan.device_code or '-'}）"
                       f"到期日 {due}，请安排保养")
            if plan.responsible_id:
                notify_user(db, plan.responsible_id, type="MAINTENANCE",
                            title="保养计划即将到期", content=content, level="P3")
            else:
                notify_roles(db, ["ADMIN", "SUPERVISOR"], type="MAINTENANCE",
                             title="保养计划即将到期", content=content, level="P3")
            sent += 1
        if sent:
            db.commit()
        logger.info(f"[Jobs][Maintenance] 到期扫描完成，提醒 {sent} 条")
        return sent
    except Exception as e:
        logger.exception(f"[Jobs][Maintenance] 扫描失败: {e}")
        return 0
    finally:
        db.close()

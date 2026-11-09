"""站内通知 API

接口清单：
  GET    /unread-count         获取当前用户未读通知数量
  GET    /                     获取通知列表（分页，可只看未读）
  POST   /{notification_id}/read   标记单条通知为已读
  POST   /read-all             标记全部已读
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import case as sa_case
from typing import List, Optional
from loguru import logger
from datetime import datetime

from app.core.database import get_db
from app.core.security import get_current_user
from app.core import alert_level as AL
from app.models.user import User
from app.models.notification import Notification

router = APIRouter()


@router.get("/unread-count")
def get_unread_count(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取未读通知数量"""
    count = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
    ).count()
    return {"count": count}


@router.get("/")
def list_notifications(
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False,
    level: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取通知列表（分页）"""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20

    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if unread_only:
        query = query.filter(Notification.is_read == False)
    if level:
        query = query.filter(Notification.level == AL.normalize(level))

    total = query.count()
    items = (
        query.order_by(Notification.is_read.asc(),
                         sa_case({'P0': 0, 'P1': 1, 'P2': 2, 'P3': 3}, value=Notification.level, else_=4),
                         Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "items": [
            {
                "id": n.id,
                "type": n.type,
                "level": n.level or "P2",
                "title": n.title,
                "content": n.content,
                "work_order_id": n.work_order_id,
                "is_read": n.is_read,
                "created_at": n.created_at.strftime("%Y-%m-%d %H:%M:%S") if n.created_at else None,
            }
            for n in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/{notification_id}/read")
def mark_read(notification_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """标记单条通知为已读"""
    notif = db.query(Notification).filter(
        Notification.id == notification_id,
        Notification.user_id == current_user.id,
    ).first()
    if not notif:
        raise HTTPException(status_code=404, detail="通知不存在或不属于当前用户")

    if not notif.is_read:
        notif.is_read = True
        db.commit()
        db.refresh(notif)
    return {"message": "已标记为已读", "id": notif.id, "is_read": notif.is_read}


@router.post("/read-all")
def mark_all_read(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """标记全部已读"""
    updated = db.query(Notification).filter(
        Notification.user_id == current_user.id,
        Notification.is_read == False,
    ).update({Notification.is_read: True}, synchronize_session="fetch")
    db.commit()
    return {"message": "全部已标记为已读", "updated": updated}


# ============================================================
# 供其他模块调用的辅助函数（不依赖登录态）
# ============================================================
def create_notification(db: Session, user_id: int, type: str, title: str, content: str,
                        work_order_id: int = None, level: str = None) -> Notification:
    """供其他模块调用的创建通知辅助函数（不需要登录态）"""
    notif = Notification(
        user_id=user_id,
        type=type,
        title=title,
        content=content,
        work_order_id=work_order_id,
        level=AL.normalize(level, default=("P3" if type == "system" else "P2")),
        is_read=False,
    )
    db.add(notif)
    db.flush()
    return notif

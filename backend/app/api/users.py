from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import Optional
from loguru import logger
from app.core.database import get_db
from app.core.security import get_current_user, require_admin, _role_value
from app.core.cache_service import cache_service
from app.core.password import hash_password
from app.models.user import User, UserRole
from app.schemas import UserCreate, UserUpdate, UserResponse, PaginatedResponse

router = APIRouter()


def _u_to_dict(u: User) -> dict:
    return {c.name: getattr(u, c.name) for c in u.__table__.columns if c.name != 'password_hash'}


def _mask_phone(phone: Optional[str]) -> Optional[str]:
    """手机号脱敏：138****0000"""
    if not phone:
        return phone
    p = str(phone)
    if len(p) < 7:
        return "***"
    return f"{p[:3]}****{p[-4:]}"


def _mask_email(email: Optional[str]) -> Optional[str]:
    """邮箱脱敏：a***@example.com"""
    if not email or "@" not in str(email):
        return email
    name, domain = str(email).split("@", 1)
    return f"{name[:1]}***@{domain}"


@router.get("/me", summary="获取当前登录用户信息")
def get_current_user_me(current_user: User = Depends(get_current_user)):
    """返回当前登录用户的完整信息（含钉钉绑定状态）"""
    return _u_to_dict(current_user)


@router.get("/", response_model=PaginatedResponse[UserResponse], summary="获取用户列表")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=1000),
    role: Optional[str] = None,
    keyword: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(User)
    if role:
        query = query.filter(User.role == role)
    if keyword:
        query = query.filter(
            User.username.ilike(f"%{keyword}%") |
            User.real_name.ilike(f"%{keyword}%")
        )
    total = query.count()
    items = query.order_by(User.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    # 安全修复：非管理员只能看到脱敏后的手机号/邮箱（派工只需要姓名+角色）
    is_admin = current_user.role == UserRole.ADMIN.value
    rows = [_u_to_dict(u) for u in items]
    if not is_admin:
        for r in rows:
            r["phone"] = _mask_phone(r.get("phone"))
            r["email"] = _mask_email(r.get("email"))
    return {"total": total, "items": rows, "page": page, "page_size": page_size}


@router.get("/login-logs", summary="登录审计记录（管理员看全部，其他角色只看自己）")
def list_login_logs(
    limit: int = Query(20, ge=1, le=200),
    only_failed: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.login_log import LoginLog
    q = db.query(LoginLog)
    if _role_value(current_user).upper() != "ADMIN":
        q = q.filter(LoginLog.user_id == current_user.id)
    if only_failed:
        q = q.filter(LoginLog.success.is_(False))
    rows = q.order_by(LoginLog.created_at.desc(), LoginLog.id.desc()).limit(limit).all()
    return {
        "items": [{
            "id": r.id,
            "username": r.username,
            "real_name": r.real_name,
            "login_type": r.login_type,
            "success": bool(r.success),
            "reason": r.reason,
            "ip": r.ip,
            "user_agent": r.user_agent,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows]
    }


@router.get("/{user_id}", response_model=UserResponse, summary="获取用户详情（带缓存）")
def get_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cache_key = f"user:{user_id}"
    cached = cache_service.get(cache_key)
    if cached:
        return cached

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    result = _u_to_dict(user)
    cache_service.set(cache_key, result, ttl=300)
    return result


@router.post("/", response_model=UserResponse, summary="创建用户（仅管理员）")
def create_user(data: UserCreate, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    existing = db.query(User).filter(User.username == data.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")
    if data.employee_id and db.query(User).filter(User.employee_id == data.employee_id).first():
        raise HTTPException(status_code=400, detail="工号已存在")
    if data.role and data.role not in {r.value for r in UserRole}:
        raise HTTPException(status_code=400, detail=f"角色不合法：{data.role}")
    data_dict = data.model_dump()
    data_dict["password_hash"] = hash_password(data_dict.pop("password"))
    user = User(**data_dict)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserResponse, summary="更新用户（管理员，或本人改自己资料）")
def update_user(
    user_id: int,
    data: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    is_admin = _role_value(current_user).upper() == "ADMIN"
    if not is_admin and current_user.id != user_id:
        raise HTTPException(status_code=403, detail="只能修改自己的资料")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    payload = data.model_dump(exclude_unset=True)
    # 非管理员只能改基础资料与密码，不能改角色/状态/工号
    if not is_admin:
        for k in ("role", "is_active", "employee_id"):
            payload.pop(k, None)
    new_password = payload.pop("password", None)
    for key, val in payload.items():
        if key in ("id", "username", "password_hash"):
            continue
        setattr(user, key, val)
    if new_password:
        user.password_hash = hash_password(new_password)
    db.commit()
    db.refresh(user)
    if new_password:
        # 密码被管理员重置：写审计（与登录共用 login_logs，可在账号安全页查看）
        try:
            from app.api.auth import _log_login
            _log_login(db, request, user, True, f"管理员 {current_user.real_name} 重置密码",
                       "password_reset", user.username)
        except Exception as e:
            logger.warning(f"[Users] 写密码重置审计失败: {e}")
    cache_service.delete(f"user:{user_id}")
    return user


@router.delete("/{user_id}", summary="删除用户（仅管理员）")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")

    # 有业务数据的人不能物理删除（工单/领用/盘点都记着他的 id，删了会撞外键报 500）
    from sqlalchemy import func, or_
    from app.models.work_order import WorkOrder
    from app.models.spare_part_requisition import SparePartRequisition
    from app.models.stocktake import Stocktake

    wo_cnt = (db.query(func.count(WorkOrder.id))
              .filter(or_(WorkOrder.technician_id == user_id,
                          WorkOrder.assignee_id == user_id,
                          WorkOrder.reporter_id == user_id,
                          WorkOrder.created_by == user_id,
                          WorkOrder.dispatcher_id == user_id))
              .scalar() or 0)
    req_cnt = (db.query(func.count(SparePartRequisition.id))
               .filter(or_(SparePartRequisition.applicant_id == user_id,
                           SparePartRequisition.approver_id == user_id))
               .scalar() or 0)
    st_cnt = (db.query(func.count(Stocktake.id))
              .filter(or_(Stocktake.created_by == user_id,
                          Stocktake.approved_by == user_id))
              .scalar() or 0)
    if wo_cnt or req_cnt or st_cnt:
        parts = []
        if wo_cnt:
            parts.append(f"工单 {wo_cnt} 张")
        if req_cnt:
            parts.append(f"领用单 {req_cnt} 张")
        if st_cnt:
            parts.append(f"盘点单 {st_cnt} 张")
        raise HTTPException(
            status_code=400,
            detail=f"该用户已有业务数据（{'、'.join(parts)}），不能直接删除；请改用「停用账号」（停用后无法登录，历史记录保留）",
        )

    # 没有业务数据：清理从属记录 + 把可空引用置空，再删账号
    from app.models.notification import Notification
    from app.models.login_log import LoginLog
    from app.models.stock_movement import StockMovement
    from app.models.customer import Customer
    from app.models.maintenance import MaintenancePlan, MaintenanceRecord
    from app.models.progress_log import WorkOrderProgressLog

    db.query(Notification).filter(Notification.user_id == user_id).delete(synchronize_session=False)
    db.query(LoginLog).filter(LoginLog.user_id == user_id).delete(synchronize_session=False)
    db.query(StockMovement).filter(StockMovement.operator_id == user_id).update(
        {"operator_id": None}, synchronize_session=False)
    db.query(Customer).filter(Customer.owner_id == user_id).update(
        {"owner_id": None}, synchronize_session=False)
    db.query(MaintenancePlan).filter(MaintenancePlan.responsible_id == user_id).update(
        {"responsible_id": None}, synchronize_session=False)
    db.query(MaintenanceRecord).filter(MaintenanceRecord.done_by_id == user_id).update(
        {"done_by_id": None}, synchronize_session=False)
    db.query(WorkOrderProgressLog).filter(WorkOrderProgressLog.operator_id == user_id).update(
        {"operator_id": None}, synchronize_session=False)

    db.delete(user)
    db.commit()
    cache_service.delete(f"user:{user_id}")
    logger.info(f"[User] {current_user.real_name} 删除账号 {user.username}")
    return {"message": "用户已删除"}


@router.post("/{user_id}/dingtalk/unbind", summary="管理员代解绑钉钉")
def admin_unbind_dingtalk(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """管理员代员工解绑钉钉账号（应对员工离职场景）"""
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="仅管理员可代解绑")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if not user.dingtalk_userid:
        raise HTTPException(status_code=400, detail="该用户未绑定钉钉")

    user.dingtalk_userid = None
    user.dingtalk_bound_at = None
    db.commit()
    cache_service.delete(f"user:{user_id}")
    logger.info(f"[User] 管理员代解绑钉钉: target_user={user_id}, admin={current_user.id}")
    return {"message": f"已解绑用户「{user.real_name}」的钉钉账号"}
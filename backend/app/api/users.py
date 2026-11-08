from fastapi import APIRouter, Depends, HTTPException, Query
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
    cache_service.delete(f"user:{user_id}")
    return user


@router.delete("/{user_id}", summary="删除用户（仅管理员）")
def delete_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录账号")
    db.delete(user)
    db.commit()
    cache_service.delete(f"user:{user_id}")
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
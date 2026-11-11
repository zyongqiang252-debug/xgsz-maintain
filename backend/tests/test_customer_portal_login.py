# -*- coding: utf-8 -*-
"""客户门户登录链路回归

背景（2026-11-11 用户反馈）：管理员在「客户管理」里创建客户后，客户拿手机号去
主站 /login 用「密码登录」，一直报「用户名或密码错误」——因为客户账号在
``customers`` 表，和内部 ``users`` 表是两套体系，主站登录根本不查客户表。

这里锁三件事：
1. 客户门户 /c/login 能正常登录（含默认密码 123456、密码错误、账号停用）；
2. 主站密码登录遇到客户手机号时，必须明确引导到客户报修入口，且**不能发内部 token**；
3. 主站验证码登录不允许把客户手机号自动注册成 TECHNICIAN（越权）。
"""
import pytest

from conftest import PREFIX, RUN, Api, db, purge_orders

_SUFFIX = str(int(RUN, 16))[-8:].rjust(8, "7")      # 纯数字尾号，避免手机号里混进 a-f
CUSTOMER_PHONE = "139" + _SUFFIX
CUSTOMER_PASSWORD = "PortalPass123"


@pytest.fixture(scope="module")
def customer(api, admin):
    st, c = api.post("/customers/", admin, json={
        "name": f"{PREFIX}门户客户{RUN}",
        "phone": CUSTOMER_PHONE,
        "password": CUSTOMER_PASSWORD,
        "company": f"{PREFIX}门户客户公司{RUN}",
    })
    assert st == 200, f"建测试客户失败：{c}"
    yield c
    # 客户是软删除（置 is_active=False），这里直接物理清掉，避免污染客户列表
    from app.models.customer import Customer
    from app.models.customer_contact import CustomerContact
    s = db()
    try:
        for row in s.query(Customer).filter(Customer.phone == CUSTOMER_PHONE).all():
            s.query(CustomerContact).filter(CustomerContact.customer_id == row.id).delete(
                synchronize_session=False)
            s.delete(row)
        s.commit()
    finally:
        s.close()


def test_customer_portal_login_ok(api, customer):
    st, body = api.post("/customer/login",
                        json={"phone": CUSTOMER_PHONE, "password": CUSTOMER_PASSWORD})
    assert st == 200, body
    assert body.get("token"), "客户登录应返回 token"
    assert body["customer"]["phone"] == CUSTOMER_PHONE


def test_customer_portal_default_password(api, admin):
    """管理员不填密码时，默认 123456 必须能登录"""
    phone = "138" + _SUFFIX
    st, c = api.post("/customers/", admin, json={"name": f"{PREFIX}默认密码{RUN}", "phone": phone})
    assert st == 200, c
    try:
        st, body = api.post("/customer/login", json={"phone": phone, "password": "123456"})
        assert st == 200, f"默认密码登录失败：{body}"
        assert body.get("token")
    finally:
        from app.models.customer import Customer
        from app.models.customer_contact import CustomerContact
        s = db()
        try:
            for row in s.query(Customer).filter(Customer.phone == phone).all():
                s.query(CustomerContact).filter(CustomerContact.customer_id == row.id).delete(
                    synchronize_session=False)
                s.delete(row)
            s.commit()
        finally:
            s.close()


def test_customer_portal_rejects_wrong_password(api, customer):
    st, body = api.post("/customer/login",
                        json={"phone": CUSTOMER_PHONE, "password": "definitely-wrong"})
    assert st == 400
    assert "密码错误" in body.get("detail", "")


def test_customer_portal_rejects_unknown_phone(api):
    st, body = api.post("/customer/login", json={"phone": "18800000000", "password": "123456"})
    assert st == 400
    assert "没有开通客户账号" in body.get("detail", "")


def test_staff_login_guides_customer_to_portal(api, customer):
    """主站密码登录：客户手机号 -> 明确引导，且绝不返回内部 token"""
    st, body = api.post("/auth/login-by-password",
                        json={"username": CUSTOMER_PHONE, "password": CUSTOMER_PASSWORD})
    assert st == 400, body
    detail = body.get("detail", "")
    assert "客户报修入口" in detail, detail
    assert "/c/login" in detail, detail
    assert not body.get("token"), "客户账号不能拿到内部登录 token"


def test_staff_login_unknown_user_keeps_generic_message(api):
    st, body = api.post("/auth/login-by-password",
                        json={"username": "18800000001", "password": "whatever"})
    assert st == 400
    assert body.get("detail") == "用户名或密码错误"


def test_customer_portal_hint_helper_units():
    """引导文案只对「客户手机号且非内部用户」生效（纯函数单测，不走 HTTP）"""
    from app.api.auth import _customer_portal_hint
    from app.models.user import User
    from app.models.customer import Customer
    from app.core.database import SessionLocal

    s = SessionLocal()
    try:
        phone = "137" + _SUFFIX
        c = Customer(name=f"{PREFIX}引导{RUN}", phone=phone, is_active=True,
                     password_hash="$2b$12$" + "x" * 53)
        s.add(c)
        s.commit()
        try:
            assert "客户报修入口" in _customer_portal_hint(s, phone)
            c.is_active = False
            s.commit()
            assert "已停用" in _customer_portal_hint(s, phone)
            # 内部员工手机号不返回客户引导
            u = s.query(User).filter(User.is_active == True).first()
            if u and u.phone:
                assert _customer_portal_hint(s, u.phone) == ""
        finally:
            s.delete(c)
            s.commit()
    finally:
        s.close()


def test_staff_code_login_does_not_promote_customer(api, customer, admin):
    """客户手机号走内部验证码登录：必须在建号前被拦下，不能变成 TECHNICIAN"""
    from app.models.user import User

    before = None
    s = db()
    try:
        before = s.query(User).filter(User.phone == CUSTOMER_PHONE).count()
    finally:
        s.close()

    st, body = api.post("/auth/send-code", json={"phone": CUSTOMER_PHONE, "scene": "login"})
    assert st == 200, body
    # 验证码只写日志，这里从后端日志里取（本地 Mock 模式）
    import re
    from pathlib import Path
    log_path = Path(__file__).resolve().parents[1] / "logs" / "app.log"
    code = None
    if log_path.exists():
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
        m = re.findall(rf"验证码 (\d{{6}}) 已生成（phone={re.escape(CUSTOMER_PHONE)}", tail)
        code = m[-1] if m else None
    st, body = api.post("/auth/login-by-code", json={"phone": CUSTOMER_PHONE, "code": code or "000000"})
    assert st == 400, f"客户手机号不应能走内部验证码登录：{body}"
    if code:
        # 验证码正确时，也必须是「去客户门户」的拒绝，而不是登录成功
        assert "客户报修入口" in body.get("detail", ""), body
    else:
        assert "验证码" in body.get("detail", ""), body

    s = db()
    try:
        assert s.query(User).filter(User.phone == CUSTOMER_PHONE).count() == before, \
            "客户手机号被自动注册成内部用户了"
    finally:
        s.close()

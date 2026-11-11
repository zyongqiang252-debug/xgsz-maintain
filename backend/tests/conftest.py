# -*- coding: utf-8 -*-
"""联动自动化测试的公共夹具

跑法（需要后端已启动）：
    cd backend
    .\\.venv\\Scripts\\python.exe -m pytest tests -v
    .\\.venv\\Scripts\\python.exe -m pytest tests -m "not slow" -v   # 跳过页面回归

约定：
- 所有测试数据带 ``PYTEST_`` 前缀 + 本次运行随机串，会话结束统一清理；
- 断言尽量「接口 + 数据库」双查：状态机不只看 200/400，还要看进度日志/通知有没有被偷偷写；
- 已知缺陷用 ``pytest.mark.xfail(strict=True)`` 标出，修好后会因 xpass 失败，提醒回来改测试。
"""
import os
import sys
import uuid
from pathlib import Path

import pytest
import requests

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

BASE = os.environ.get("XGSZ_BASE", "http://127.0.0.1:18080")
API = BASE + "/api/v1"
RUN = uuid.uuid4().hex[:6]
PREFIX = "PYTEST_"
TECH_PASSWORD = "PytestPass123"


# ============================================================
# 基础 HTTP
# ============================================================
class Api:
    def __init__(self):
        self.s = requests.Session()

    def call(self, method, path, token=None, **kw):
        headers = kw.pop("headers", {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        r = self.s.request(method, API + path, headers=headers, timeout=kw.pop("timeout", 60), **kw)
        try:
            body = r.json()
        except Exception:
            body = {"_text": (r.text or "")[:300]}
        return r.status_code, body

    def get(self, path, token=None, **kw):
        return self.call("GET", path, token, **kw)

    def post(self, path, token=None, **kw):
        return self.call("POST", path, token, **kw)

    def put(self, path, token=None, **kw):
        return self.call("PUT", path, token, **kw)

    def delete(self, path, token=None, **kw):
        return self.call("DELETE", path, token, **kw)


def login(api, username, password):
    st, body = api.post("/auth/login-by-password", json={"username": username, "password": password})
    return (body.get("token") or body.get("access_token")), body, st


# ============================================================
# 数据库断言与清理
# ============================================================
def db():
    from app.core.database import SessionLocal
    return SessionLocal()


def progress_log_count(work_order_id):
    from app.models.progress_log import WorkOrderProgressLog
    s = db()
    try:
        return (s.query(WorkOrderProgressLog)
                .filter(WorkOrderProgressLog.work_order_id == work_order_id).count())
    finally:
        s.close()


def notification_count(work_order_id):
    from app.models.notification import Notification
    s = db()
    try:
        return (s.query(Notification).filter(Notification.work_order_id == work_order_id).count())
    finally:
        s.close()


def workload_of(user_id):
    from app.models.user import User
    s = db()
    try:
        u = s.query(User).filter(User.id == user_id).first()
        return int(u.current_workload_count or 0) if u else None
    finally:
        s.close()


def purge_orders(fault_prefix=PREFIX):
    """删掉本次测试创建的工单（含子表与外部引用），不影响业务数据"""
    from app.models.customer import Customer  # noqa
    from app.models.device import Device  # noqa
    from app.models.notification import Notification
    from app.models.part_instance import PartInstance
    from app.models.progress_log import WorkOrderProgressLog
    from app.models.spare_part_requisition import SparePartRequisition
    from app.models.stock_movement import StockMovement
    from app.models.work_order import WorkOrder
    from app.models.work_order_collaborator import WorkOrderCollaborator
    from app.models.work_order_edit_log import WorkOrderEditLog

    s = db()
    try:
        wos = s.query(WorkOrder).filter(WorkOrder.fault_description.like(f"{fault_prefix}%")).all()
        ids = [w.id for w in wos]
        if ids:
            for model in (StockMovement, PartInstance, SparePartRequisition):
                s.query(model).filter(model.work_order_id.in_(ids)).update(
                    {"work_order_id": None}, synchronize_session=False)
            for model in (WorkOrderProgressLog, WorkOrderEditLog, WorkOrderCollaborator):
                s.query(model).filter(model.work_order_id.in_(ids)).delete(synchronize_session=False)
            s.query(Notification).filter(Notification.work_order_id.in_(ids)).delete(synchronize_session=False)
            s.query(WorkOrder).filter(WorkOrder.id.in_(ids)).delete(synchronize_session=False)
        # 并发用例造的客户/设备
        devs = s.query(Device).filter(Device.device_code.like(f"{fault_prefix}%")).all()
        for d in devs:
            s.delete(d)
        for c in s.query(Customer).filter(Customer.name.like(f"{fault_prefix}%")).all():
            s.delete(c)
        s.commit()
    finally:
        s.close()


def purge_user(user_id):
    from app.models.customer import Customer
    from app.models.login_log import LoginLog
    from app.models.notification import Notification
    from app.models.stock_movement import StockMovement
    from app.models.user import User
    from app.models.work_order import WorkOrder

    s = db()
    try:
        for col in (WorkOrder.technician_id, WorkOrder.assignee_id, WorkOrder.reporter_id,
                    WorkOrder.created_by, WorkOrder.dispatcher_id):
            s.query(WorkOrder).filter(col == user_id).update({col.key: None}, synchronize_session=False)
        s.query(StockMovement).filter(StockMovement.operator_id == user_id).update(
            {"operator_id": None}, synchronize_session=False)
        s.query(Customer).filter(Customer.owner_id == user_id).update(
            {"owner_id": None}, synchronize_session=False)
        s.query(Notification).filter(Notification.user_id == user_id).delete(synchronize_session=False)
        s.query(LoginLog).filter(LoginLog.user_id == user_id).delete(synchronize_session=False)
        s.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        s.commit()
    finally:
        s.close()


# ============================================================
# 夹具
# ============================================================
@pytest.fixture(scope="session")
def api():
    return Api()


@pytest.fixture(scope="session")
def server():
    try:
        r = requests.get(BASE + "/health", timeout=3)
        assert r.json().get("status") == "healthy"
    except Exception as e:
        pytest.skip(f"后端未启动或不可用（{BASE}）：{e}")
    return BASE


@pytest.fixture(scope="session")
def admin(api, server):
    token, body, st = login(api, "admin", "admin123")
    assert st == 200 and token, f"管理员登录失败：{body}"
    return token


@pytest.fixture(scope="session")
def techs(api, admin):
    """两个临时技术员：一个当「负责人」，一个当「新负责人」"""
    made = []
    for tag in ("a", "b"):
        username = f"pytest_tech_{tag}_{RUN}"
        st, u = api.post("/users/", admin, json={
            "username": username, "password": TECH_PASSWORD,
            "real_name": f"Pytest技术员{tag.upper()}{RUN}", "role": "TECHNICIAN"})
        assert st in (200, 201), f"建测试技术员失败：{u}"
        token, _, lst = login(api, username, TECH_PASSWORD)
        assert lst == 200, "测试技术员登录失败"
        made.append({"id": u["id"], "username": username, "token": token})
    yield {"a": made[0], "b": made[1]}
    for t in made:
        purge_user(t["id"])


@pytest.fixture(scope="session", autouse=True)
def cleanup(api, admin, server):
    """会话结束清理测试工单（即使用例中途失败也会清）"""
    yield
    try:
        purge_orders()
    except Exception as e:
        print(f"[cleanup] 清理测试工单失败：{e}")


@pytest.fixture
def builder(api, admin, techs):
    """建单 + 推进到目标状态的小工具"""
    return OrderBuilder(api, admin, techs)


class OrderBuilder:
    """按状态机把一张 PYTEST 工单推到指定状态"""

    def __init__(self, api, admin, techs):
        self.api, self.admin, self.techs = api, admin, techs

    def create(self, **extra):
        payload = {"fault_description": f"{PREFIX}{extra.pop('case', 'order')} {RUN}", "priority": "P2"}
        payload.update(extra)
        st, wo = self.api.post("/work-orders/", self.admin, json=payload)
        assert st in (200, 201), f"建单失败：{wo}"
        return wo

    def move(self, wid, to, token=None, **extra):
        return self.api.post(f"/work-orders/{wid}/transition", token or self.admin,
                             json={"to_status": to, **extra})

    def to(self, status, case="order", technician_id=None, **extra):
        """建一张单并推进到 status；technician_id 指定负责人（默认用技术员 A）"""
        tech_default = technician_id or self.techs["a"]["id"]
        wo = self.create(case=case, **extra)
        wid = wo["id"]
        path = {
            "DRAFT": [],
            "SUBMITTED": ["SUBMITTED"],
            "ASSIGNED": ["SUBMITTED", "ASSIGNED"],
            "ACCEPTED": ["SUBMITTED", "ASSIGNED", "ACCEPTED"],
            "ARRIVED": ["SUBMITTED", "ASSIGNED", "ACCEPTED", "ARRIVED"],
            "INSPECTING": ["SUBMITTED", "ASSIGNED", "ACCEPTED", "ARRIVED", "INSPECTING"],
            "IN_PROGRESS": ["SUBMITTED", "ASSIGNED", "ACCEPTED", "ARRIVED", "INSPECTING", "IN_PROGRESS"],
            "ARCHIVING": ["SUBMITTED", "ASSIGNED", "ACCEPTED", "ARRIVED", "INSPECTING",
                          "IN_PROGRESS", "ARCHIVING"],
            "ARCHIVED": ["SUBMITTED", "ASSIGNED", "ACCEPTED", "ARRIVED", "INSPECTING",
                         "IN_PROGRESS", "ARCHIVING"],
            "REJECTED": ["SUBMITTED", "REJECTED"],
            "COMPLETED": ["SUBMITTED", "ASSIGNED", "ACCEPTED", "ARRIVED", "INSPECTING",
                          "IN_PROGRESS"],
        }[status]
        for i, to in enumerate(path):
            extra_args = {}
            if to in ("ASSIGNED", "ACCEPTED", "ARRIVED", "INSPECTING", "IN_PROGRESS") and i == 1:
                extra_args["technician_id"] = tech_default
            st, body = self.move(wid, to, **extra_args)
            assert st == 200, f"推进到 {to} 失败：{st} {body}"
        if status == "ARCHIVED":
            self.fill_fields(wid)
            st, body = self.api.post(f"/work-orders/{wid}/archive-complete", self.admin)
            assert st == 200, f"归档失败：{st} {body}"
        elif status == "COMPLETED":
            # /complete 是唯一把工单打到 COMPLETED 的入口
            self.fill_fields(wid)
            st, body = self.api.post(f"/work-orders/{wid}/complete", self.admin)
            assert st == 200, f"提交完成失败：{st} {body}"
        return self.get(wid)

    def fill_fields(self, wid):
        st, body = self.api.put(f"/work-orders/{wid}", self.admin, json={
            "fault_phenomenon": "探针：运行中掉卡",
            "root_cause": "GPU 卡故障",
            "solution_steps": "1. 停机 2. 换卡 3. 压测",
            "repair_result": "已修复",
            "work_hours": 1.5,
        })
        assert st == 200, f"填归档字段失败：{body}"

    def get(self, wid):
        st, body = self.api.get(f"/work-orders/{wid}", self.admin)
        assert st == 200, f"查工单失败：{body}"
        return body

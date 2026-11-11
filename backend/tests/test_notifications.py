# -*- coding: utf-8 -*-
"""消息通知联动：P0/P1/P2 补的那批通知是否真的发到了该收的人手里

覆盖：
- P0 领用四事件（申请/批准/驳回/发料）、盘点两事件（提交/审批）、改派新负责人
- P1 工单挂起/恢复、维修完成待归档、出库跌破安全线（站内）、巡检异常
- P2 备件返厂/报废、保养到期扫描、请假撤销

约定：每条用例先用 ``max_notification_id()`` 记水位，再断言「新增通知」的类型/标题/收件人，
避免历史通知干扰；操作人自己不应收到自己触发的通知。
"""
import uuid
from datetime import datetime, timedelta

from conftest import (PREFIX, max_notification_id, notifications_after)


def _me(api, token):
    st, body = api.get("/users/me", token)
    assert st == 200
    return body


def _mk_part(api, admin, stock=3, safety=2, need_sn=False, warehouse_id=None):
    code = f"{PREFIX}PART-{uuid.uuid4().hex[:6]}"
    payload = {
        "part_code": code, "part_name": f"Pytest备件{code[-4:]}", "unit": "个",
        "stock_quantity": stock, "safety_stock": safety, "unit_price": 100,
        "need_sn": need_sn}
    if warehouse_id:
        payload["warehouse_id"] = warehouse_id
    st, part = api.post("/spare-parts/", admin, json=payload)
    assert st in (200, 201), part
    return part


# ============================================================
# P0：领用四事件
# ============================================================
def test_requisition_submit_approve_issue_notifications(api, admin, techs, supervisor, builder):
    admin_id = _me(api, admin)["id"]
    part = _mk_part(api, admin)
    wo = builder.to("IN_PROGRESS", case="notify-req", technician_id=techs["a"]["id"])
    marker = max_notification_id()

    # 1) 技术员提交 → 管理员 + 主管收到「待审批」，本人不收
    st, req = api.post("/spare-parts/requisitions/", techs["a"]["token"], json={
        "part_id": part["id"], "quantity": 1, "reason": "Pytest 领用",
        "work_order_id": wo["id"]})
    assert st in (200, 201), req
    for uid in (admin_id, supervisor["id"]):
        notes = notifications_after(uid, marker, "REQUISITION")
        assert notes, f"用户 {uid} 没收到待审批通知"
        assert "待审批" in notes[-1]["title"]
    assert not notifications_after(techs["a"]["id"], marker, "REQUISITION"), "申请人不应收到自己的申请通知"

    # 2) 审批通过 → 申请人收到「已批准」
    marker = max_notification_id()
    st, _ = api.post(f"/spare-parts/requisitions/{req['id']}/approve", admin)
    assert st == 200
    notes = notifications_after(techs["a"]["id"], marker, "REQUISITION")
    assert notes and "批准" in notes[-1]["title"], notes
    assert not notifications_after(admin_id, marker, "REQUISITION"), "审批人不应收到自己触发的通知"

    # 3) 发料 → 申请人收到「已发料」（带 SN 或工单信息）
    marker = max_notification_id()
    st, _ = api.post(f"/spare-parts/requisitions/{req['id']}/issue", admin, json={"remark": "Pytest 发料"})
    assert st == 200
    notes = notifications_after(techs["a"]["id"], marker, "REQUISITION")
    assert notes and "发料" in notes[-1]["title"], notes


def test_requisition_reject_and_cancel_notifications(api, admin, techs, supervisor, builder):
    admin_id = _me(api, admin)["id"]
    part = _mk_part(api, admin)
    wo = builder.to("IN_PROGRESS", case="notify-req2", technician_id=techs["a"]["id"])

    # 驳回 → 申请人收到带原因
    st, req = api.post("/spare-parts/requisitions/", techs["a"]["token"], json={
        "part_id": part["id"], "quantity": 1, "reason": "Pytest 驳回",
        "work_order_id": wo["id"]})
    marker = max_notification_id()
    st, body = api.post(f"/spare-parts/requisitions/{req['id']}/reject", supervisor["token"],
                        json={"reject_reason": "Pytest 库存归零计划"})
    assert st == 200, body
    notes = notifications_after(techs["a"]["id"], marker, "REQUISITION")
    assert notes and "驳回" in notes[-1]["title"] and "库存归零" in notes[-1]["content"], notes

    # 撤销 → 主管/管理员收到「已撤销」
    st, req2 = api.post("/spare-parts/requisitions/", techs["a"]["token"], json={
        "part_id": part["id"], "quantity": 1, "reason": "Pytest 撤销",
        "work_order_id": wo["id"]})
    marker = max_notification_id()
    st, _ = api.post(f"/spare-parts/requisitions/{req2['id']}/cancel", techs["a"]["token"])
    assert st == 200
    notes = notifications_after(supervisor["id"], marker, "REQUISITION")
    assert notes and "撤销" in notes[-1]["title"], notes
    assert not notifications_after(techs["a"]["id"], marker, "REQUISITION"), "撤销人自己不应收到通知"
    assert admin_id  # 管理员同样会收到，这里只断言主管


# ============================================================
# P0：盘点两事件
# ============================================================
def test_stocktake_submit_and_approve_notifications(api, admin, techs, supervisor):
    admin_id = _me(api, admin)["id"]
    st, wh = api.post("/warehouses/", admin, json={
        "code": f"{PREFIX}WH-{uuid.uuid4().hex[:6]}", "name": "Pytest仓"})
    assert st in (200, 201), wh
    _mk_part(api, admin, warehouse_id=wh["id"])
    st, take = api.post("/stocktakes/", admin,
                        json={"warehouse_id": wh["id"], "remark": f"{PREFIX}盘点"})
    assert st in (200, 201), take
    st, detail = api.get(f"/stocktakes/{take['id']}", admin)
    items = detail.get("items") or []
    assert items
    counts = [{"item_id": i["id"], "actual_qty": float(i.get("system_qty") or 0)} for i in items]
    api.post(f"/stocktakes/{take['id']}/count", techs["a"]["token"], json={"items": counts})

    marker = max_notification_id()
    st, _ = api.post(f"/stocktakes/{take['id']}/submit", techs["a"]["token"])
    assert st == 200
    notes = notifications_after(supervisor["id"], marker, "STOCKTAKE")
    assert notes and "待审批" in notes[-1]["title"], notes

    marker = max_notification_id()
    st, _ = api.post(f"/stocktakes/{take['id']}/approve", supervisor["token"], json={})
    assert st == 200
    notes = notifications_after(admin_id, marker, "STOCKTAKE")
    assert notes and "已确认" in notes[-1]["title"], notes


# ============================================================
# P0：改派补新负责人
# ============================================================
def test_reassign_notifies_new_owner(builder, api, techs):
    wo = builder.to("ASSIGNED", case="notify-reassign", technician_id=techs["a"]["id"])
    marker = max_notification_id()
    st, body = builder.move(wo["id"], "ASSIGNED", technician_id=techs["b"]["id"], remark="Pytest 换人")
    assert st == 200, body
    new_notes = notifications_after(techs["b"]["id"], marker, "WORK_ORDER")
    old_notes = notifications_after(techs["a"]["id"], marker, "WORK_ORDER")
    # 新负责人收到的是派工通知（内容带「改派：A → B」），旧负责人收到「已转出」
    assert any("派工" in n["title"] and "改派" in n["content"] for n in new_notes), new_notes
    assert old_notes and "转出" in old_notes[-1]["title"], old_notes


# ============================================================
# P1：挂起 / 恢复 / 待归档
# ============================================================
def test_hold_and_resume_notifications(builder, api, techs, admin, supervisor):
    wo = builder.to("IN_PROGRESS", case="notify-hold", technician_id=techs["a"]["id"])
    marker = max_notification_id()
    st, body = api.post(f"/work-orders/{wo['id']}/hold", techs["a"]["token"],
                        json={"reason": "VENDOR", "remark": "Pytest 等厂商"})
    assert st == 200, body
    notes = notifications_after(techs["a"]["id"], marker, "WORK_ORDER")
    assert not notes, "挂起人自己不应收到挂起通知"
    assert notifications_after(supervisor["id"], marker, "WORK_ORDER"), "主管应收到挂起通知"

    marker = max_notification_id()
    st, body = api.post(f"/work-orders/{wo['id']}/resume", techs["a"]["token"])
    assert st == 200, body
    assert notifications_after(supervisor["id"], marker, "WORK_ORDER"), "主管应收到恢复通知"


def test_archiving_notifies_supervisor(builder, api, techs, supervisor):
    wo = builder.to("IN_PROGRESS", case="notify-archive", technician_id=techs["a"]["id"])
    marker = max_notification_id()
    st, body = builder.move(wo["id"], "ARCHIVING", token=techs["a"]["token"], remark="Pytest 维修完成")
    assert st == 200, body
    notes = notifications_after(supervisor["id"], marker, "WORK_ORDER")
    assert notes and "待归档" in notes[-1]["title"], notes


# ============================================================
# P1：出库跌破安全线 → 站内
# ============================================================
def test_low_stock_inapp_alert(api, admin, supervisor):
    sup_id = supervisor["id"]
    part = _mk_part(api, admin, stock=3, safety=2)
    marker = max_notification_id()
    st, body = api.post(f"/spare-parts/{part['id']}/consume", admin,
                        json={"quantity": 2, "remark": "Pytest 跌破安全线"})
    assert st == 200, body
    notes = notifications_after(sup_id, marker, "STOCK_ALERT")
    assert notes and "安全库存" in notes[-1]["title"], notes


# ============================================================
# P1：巡检异常
# ============================================================
def test_inspection_abnormal_notification(api, admin, techs, supervisor):
    st, tpl = api.post("/inspections/templates", admin, json={
        "name": f"{PREFIX}点检模板{uuid.uuid4().hex[:4]}", "device_type": "GPU服务器",
        "active": True, "items": [{"name": "GPU 温度", "standard": "<85℃"}]})
    assert st in (200, 201), tpl
    marker = max_notification_id()
    st, body = api.post("/inspections/records", techs["a"]["token"], json={
        "template_id": tpl["id"], "device_code": f"{PREFIX}DEV-{uuid.uuid4().hex[:4]}",
        "results": [{"name": "GPU 温度", "ok": False, "value": "95℃"}],
        "create_work_order_on_abnormal": False})
    assert st == 200, body
    notes = notifications_after(supervisor["id"], marker, "INSPECTION")
    assert notes and "异常" in notes[-1]["title"], notes


# ============================================================
# P2：备件返厂 / 报废
# ============================================================
def test_part_instance_rma_and_scrap_notifications(api, admin, techs, supervisor):
    part = _mk_part(api, admin, stock=2, safety=0, need_sn=True)
    sn = f"{PREFIX}SN-{uuid.uuid4().hex[:4]}"
    st, body = api.post(f"/spare-parts/{part['id']}/stock-in", admin,
                        json={"quantity": 1, "serial_no": sn})
    assert st == 200, body
    st, insts = api.get("/part-instances/", admin,
                        params={"part_id": part["id"], "page_size": 10})
    inst = (insts.get("items") or [])[0]

    marker = max_notification_id()
    st, body = api.post(f"/part-instances/{inst['id']}/rma", techs["a"]["token"],
                        json={"remark": "Pytest 返厂"})
    assert st == 200, body
    notes = notifications_after(supervisor["id"], marker, "PART")
    assert notes and "返厂" in notes[-1]["title"], notes

    marker = max_notification_id()
    st, body = api.post(f"/part-instances/{inst['id']}/scrap", techs["a"]["token"],
                        json={"remark": "Pytest 报废"})
    assert st == 200, body
    notes = notifications_after(supervisor["id"], marker, "PART")
    assert notes and "报废" in notes[-1]["title"], notes


# ============================================================
# P2：保养到期扫描
# ============================================================
def test_maintenance_due_scan(api, admin, techs):
    from app.core.periodic_jobs import run_maintenance_due_check

    due = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    st, plan = api.post("/maintenance/plans", admin, json={
        "plan_name": f"{PREFIX}保养-{uuid.uuid4().hex[:4]}",
        "device_code": "PYTEST-DEV", "cycle_type": "DAYS", "cycle_value": 30,
        "responsible_id": techs["a"]["id"], "next_due_at": due, "status": "ACTIVE"})
    assert st in (200, 201), plan
    marker = max_notification_id()
    run_maintenance_due_check(days_ahead=3)
    notes = notifications_after(techs["a"]["id"], marker, "MAINTENANCE")
    assert notes and "到期" in notes[-1]["title"], notes

    # 24 小时内不重复提醒
    run_maintenance_due_check(days_ahead=3)
    again = notifications_after(techs["a"]["id"], marker, "MAINTENANCE")
    assert len(again) == 1, f"保养提醒重复发送：{len(again)} 条"


# ============================================================
# P2：请假撤销
# ============================================================
def test_leave_cancel_notification(api, techs, supervisor):
    st, lr = api.post("/leave-requests/", techs["a"]["token"], json={
        "correlation_id": f"{PREFIX}LEAVE-{uuid.uuid4().hex[:6]}",
        "leave_type": "PERSONAL", "leave_reason": "Pytest 请假",
        "date_from": "2026-12-20", "date_to": "2026-12-20", "shift_of_range": "ALL_DAY"})
    assert st in (200, 201), lr
    marker = max_notification_id()
    st, body = api.post(f"/leave-requests/{lr['id']}/cancel", techs["a"]["token"])
    assert st == 200, body
    notes = notifications_after(supervisor["id"], marker, "LEAVE")
    assert notes and "撤销" in notes[-1]["title"], notes

# ============================================================
# 申请人自助领料（方案 B）
# ============================================================
def test_applicant_can_self_issue_but_not_others(api, admin, techs, supervisor, builder):
    part = _mk_part(api, admin, stock=2, safety=0)
    wo = builder.to("IN_PROGRESS", case="notify-req3", technician_id=techs["a"]["id"])
    st, req = api.post("/spare-parts/requisitions/", techs["a"]["token"], json={
        "part_id": part["id"], "quantity": 1, "reason": "Pytest 自助领料",
        "work_order_id": wo["id"]})
    assert st in (200, 201), req
    st, body = api.post(f"/spare-parts/requisitions/{req['id']}/approve", admin)
    assert st == 200, body

    marker = max_notification_id()
    st, body = api.post(f"/spare-parts/requisitions/{req['id']}/issue", techs["a"]["token"],
                        json={"remark": "Pytest 自助领料"})
    assert st == 200 and body.get("status") == "ISSUED", body
    # 主管收到「申请人自助」留痕通知；本人操作不给自己发
    notes = notifications_after(supervisor["id"], marker, "REQUISITION")
    assert notes and "自助" in notes[-1]["title"], notes
    assert not notifications_after(techs["a"]["id"], marker, "REQUISITION"), "自助领料人不应收到自己的通知"

    # 别人的单不能发：admin 申请并批准，技术员 B 去发 → 403
    st, req2 = api.post("/spare-parts/requisitions/", admin, json={
        "part_id": part["id"], "quantity": 1, "reason": "Pytest 代发校验"})
    assert st in (200, 201), req2
    st, _ = api.post(f"/spare-parts/requisitions/{req2['id']}/approve", admin)
    assert st == 200
    st, body = api.post(f"/spare-parts/requisitions/{req2['id']}/issue", techs["b"]["token"],
                        json={"remark": "越权发别人的单"})
    assert st == 403, f"非申请人/非主管不应能发料：{st} {body}"
    api.post(f"/spare-parts/requisitions/{req2['id']}/cancel", admin)

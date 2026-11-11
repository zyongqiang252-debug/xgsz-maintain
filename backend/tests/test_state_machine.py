# -*- coding: utf-8 -*-
"""状态机矩阵：合法流转要生效，非法流转必须「无副作用」地拒绝

规格来源：``app/api/work_orders.py`` 的 ``VALID_TRANSITIONS`` + 挂起/改派/远程特例。
出口标准（测试方案 §4）：合法=200 且状态变更；非法=400 且状态不变，
**并且不能偷偷写进度日志 / 通知 / 工作量**。
"""
import pytest

from conftest import notification_count, progress_log_count

# COMPLETED 是历史状态：/complete 现在置 ARCHIVING，接口已无法把工单打到 COMPLETED
STATES = ["DRAFT", "SUBMITTED", "ASSIGNED", "ACCEPTED", "ARRIVED", "INSPECTING",
          "IN_PROGRESS", "ARCHIVING", "ARCHIVED", "REJECTED"]

# 规格表：每个状态允许的目标状态（不含「同状态改派」，那条单独测）
LEGAL = {
    "DRAFT": ["SUBMITTED", "ASSIGNED"],
    "SUBMITTED": ["ASSIGNED", "REJECTED"],
    "ASSIGNED": ["ACCEPTED", "SUBMITTED", "REJECTED"],
    "ACCEPTED": ["ARRIVED", "REJECTED"],
    "ARRIVED": ["INSPECTING", "REJECTED"],
    "INSPECTING": ["IN_PROGRESS", "REJECTED"],
    "IN_PROGRESS": ["ARCHIVING", "REJECTED"],
    "ARCHIVING": ["ARCHIVED"],
    "ARCHIVED": [],
    "REJECTED": [],
}
REASSIGNABLE = ["ASSIGNED", "ACCEPTED", "ARRIVED", "INSPECTING"]

ILLEGAL_PAIRS = [
    (f, t) for f in STATES for t in STATES
    if t not in LEGAL[f] and f not in ("ARCHIVED", "REJECTED")
]


@pytest.mark.parametrize("from_status,to_status", ILLEGAL_PAIRS)
def test_illegal_transition_rejected_without_side_effects(builder, from_status, to_status):
    """非法流转：400 + 状态不变 + 不写日志/通知"""
    wo = builder.to(from_status, case=f"illegal-{from_status}-{to_status}")
    wid = wo["id"]
    logs_before = progress_log_count(wid)
    notes_before = notification_count(wid)

    st, body = builder.move(wid, to_status)

    assert st == 400, f"{from_status} → {to_status} 应被拒绝，实际 {st} {body}"
    assert body.get("detail"), "400 必须给出可读原因"
    after = builder.get(wid)
    assert after["status"] == from_status, f"非法流转改动了状态：{after['status']}"
    assert progress_log_count(wid) == logs_before, "非法流转不应写进度日志"
    assert notification_count(wid) == notes_before, "非法流转不应发通知"


def test_happy_path_all_steps(builder):
    """DRAFT→SUBMITTED→ASSIGNED→ACCEPTED→ARRIVED→INSPECTING→IN_PROGRESS→ARCHIVING→ARCHIVED"""
    wo = builder.to("ARCHIVED", case="happy-path")
    assert wo["status"] == "ARCHIVED"
    logs = progress_log_count(wo["id"])
    assert logs >= 8, f"全链路应至少 8 条进度日志，实际 {logs}"


def test_draft_can_assign_directly(builder):
    wo = builder.create(case="draft-assign")
    st, body = builder.move(wo["id"], "ASSIGNED", technician_id=builder.techs["a"]["id"])
    assert st == 200, body
    assert body["status"] == "ASSIGNED"


def test_reject_from_submitted(builder):
    wo = builder.to("SUBMITTED", case="reject")
    st, body = builder.move(wo["id"], "REJECTED", remark="信息不全")
    assert st == 200, body
    assert body["status"] == "REJECTED"


def test_reject_to_pool_requires_remark(builder):
    """ASSIGNED → SUBMITTED（拒收回池）必须写原因"""
    wo = builder.to("ASSIGNED", case="reject-no-remark")
    st, body = builder.move(wo["id"], "SUBMITTED")
    assert st == 400 and "原因" in str(body.get("detail")), f"空原因应被拒：{st} {body}"
    st, body = builder.move(wo["id"], "SUBMITTED", remark="现场无法处理")
    assert st == 200 and body["status"] == "SUBMITTED"


@pytest.mark.parametrize("state", ["ASSIGNED", "ACCEPTED", "ARRIVED", "INSPECTING"])
def test_reassign_in_allowed_states(builder, state):
    """同状态改派：仅 已派单/已接单/已到场/检查中 四个状态允许"""
    wo = builder.to(state, case=f"reassign-{state}")
    tech_b = builder.techs["b"]["id"]
    st, body = builder.move(wo["id"], state, technician_id=tech_b, remark="换人")
    assert st == 200, f"{state} 改派应允许：{st} {body}"
    assert builder.get(wo["id"])["technician_id"] == tech_b


@pytest.mark.parametrize("state", ["DRAFT", "SUBMITTED", "IN_PROGRESS", "ARCHIVING", "ARCHIVED"])
def test_reassign_rejected_in_other_states(builder, state):
    """非四个改派状态，同状态请求应 400"""
    wo = builder.to(state, case=f"no-reassign-{state}")
    st, body = builder.move(wo["id"], state, technician_id=builder.techs["b"]["id"], remark="换人")
    assert st == 400, f"{state} 不应允许改派：{st} {body}"


def test_hold_blocks_all_transitions(builder):
    """挂起中任何流转都必须 400，且状态不变；恢复后可继续"""
    wo = builder.to("IN_PROGRESS", case="hold-block")
    st, body = builder.api.post(f"/work-orders/{wo['id']}/hold", builder.admin,
                                json={"reason": "VENDOR", "remark": "等厂商"})
    assert st == 200, body
    for target in ("ARCHIVING", "REJECTED", "IN_PROGRESS"):
        st, body = builder.move(wo["id"], target)
        assert st == 400, f"挂起中 {target} 应被拒：{st} {body}"
        assert builder.get(wo["id"])["status"] == "IN_PROGRESS"
    st, body = builder.api.post(f"/work-orders/{wo['id']}/resume", builder.admin)
    assert st == 200, body
    st, body = builder.move(wo["id"], "ARCHIVING")
    assert st == 200, "恢复后应可继续流转"


@pytest.mark.xfail(strict=True, reason="C-01 已知缺陷：改派分支在挂起检查之前 return，挂起中仍可改派")
def test_hold_blocks_reassign(builder):
    """挂起中改派应被拒绝（当前 200，负责人被换掉）"""
    wo = builder.to("ACCEPTED", case="hold-reassign")
    builder.api.post(f"/work-orders/{wo['id']}/hold", builder.admin,
                     json={"reason": "VENDOR", "remark": "等厂商"})
    st, body = builder.move(wo["id"], "ACCEPTED", technician_id=builder.techs["b"]["id"], remark="改派")
    assert st == 400, f"挂起中改派应被拒，实际 {st}，负责人已变成 {builder.get(wo['id'])['technician_id']}"


@pytest.mark.parametrize("terminal", ["ARCHIVED", "REJECTED"])
def test_terminal_states_reject_everything(builder, terminal):
    """终态不可逆：任何目标都 400，且状态不变"""
    wo = builder.to(terminal, case=f"terminal-{terminal}")
    for target in STATES:
        st, body = builder.move(wo["id"], target)
        assert st == 400, f"{terminal} → {target} 应被拒：{st} {body}"
        assert builder.get(wo["id"])["status"] == terminal


def test_remote_mode_skips_arrival(builder):
    """REMOTE/RMA/VENDOR：ACCEPTED 可直接进 IN_PROGRESS；现场模式不行（后者在非法矩阵里）"""
    wo = builder.create(case="remote-skip", service_mode="REMOTE")
    wid = wo["id"]
    tech = builder.techs["a"]["id"]
    for to, extra in (("SUBMITTED", {}), ("ASSIGNED", {"technician_id": tech}), ("ACCEPTED", {})):
        st, body = builder.move(wid, to, **extra)
        assert st == 200, f"{to} 失败：{body}"
    st, body = builder.move(wid, "IN_PROGRESS")
    assert st == 200 and body["status"] == "IN_PROGRESS", f"远程模式应跳过到场：{st} {body}"


def test_illegal_transition_message_lists_allowed(builder):
    """跳过阶段时，错误信息要给出允许的目标状态（照着改得动）"""
    wo = builder.to("SUBMITTED", case="skip-stage")
    st, body = builder.move(wo["id"], "IN_PROGRESS")
    assert st == 400
    assert "允许的目标状态" in body["detail"], body

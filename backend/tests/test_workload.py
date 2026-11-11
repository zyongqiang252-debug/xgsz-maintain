# -*- coding: utf-8 -*-
"""工作量守恒与扣减时点

实测（2026-11-11）发现的真实语义，比测试方案原来的假设更糟：
- 派工（→ASSIGNED）**+1**，这一条对；
- 但**接单（ASSIGNED→ACCEPTED）也 -1**——`_update_workload` 把「离开 ASSIGNED」一律当成回退，
  于是「在办工作量」只在「待接单」那一刻是 1，接单后就归零；
- 归档完成 / 提交完成都没有扣减动作（此时通常已经是 0，看不出来）。

期望语义（本文件断言）：
    派工 +1 → 接单保持 +1 → 拒收/归档/完成 -1。
    派工→拒收循环 3 次，两人工作量之和回到起点（守恒）。
"""
import pytest

from conftest import workload_of


def test_reject_loop_conservation(builder, techs):
    """派工→拒收 循环 3 轮，两人工作量之和回到起点"""
    a, b = techs["a"]["id"], techs["b"]["id"]
    base = {a: workload_of(a), b: workload_of(b)}

    for i in range(3):
        tech_id = a if i % 2 == 0 else b
        wo = builder.to("ASSIGNED", case=f"workload-reject-{i}", technician_id=tech_id)
        assert workload_of(tech_id) == base[tech_id] + 1, f"第 {i} 轮派工后 {tech_id} 应 +1"

        st, body = builder.move(wo["id"], "SUBMITTED", remark="现场无法处理")
        assert st == 200, f"拒收失败：{st} {body}"
        assert workload_of(a) == base[a], f"第 {i} 轮拒收后 A 未回退"
        assert workload_of(b) == base[b], f"第 {i} 轮拒收后 B 未回退"

    assert workload_of(a) + workload_of(b) == base[a] + base[b], "守恒律被破坏"


def test_reject_keeps_other_technician_untouched(builder, techs):
    """A 被拒收，不应动到 B 的工作量"""
    a, b = techs["a"]["id"], techs["b"]["id"]
    base_b = workload_of(b)
    wo = builder.to("ASSIGNED", case="reject-isolation", technician_id=a)
    st, body = builder.move(wo["id"], "SUBMITTED", remark="换人处理")
    assert st == 200, body
    assert workload_of(b) == base_b


@pytest.mark.xfail(strict=True, reason="C-02 修订版：接单（ASSIGNED→ACCEPTED）就把工作量 -1，在办工作量被清零")
def test_accept_keeps_workload(builder, techs):
    """接单后工作量应保持 +1（只有拒收/归档/完成才回退）"""
    a = techs["a"]["id"]
    base = workload_of(a)
    wo = builder.to("ASSIGNED", case="workload-accept", technician_id=a)
    assert workload_of(a) == base + 1, "派工后应 +1"
    st, body = builder.move(wo["id"], "ACCEPTED")
    assert st == 200, body
    assert workload_of(a) == base + 1, f"接单后工作量不应回退，实际 {workload_of(a)}"


@pytest.mark.xfail(strict=True, reason="C-02 修订版：接单即清零 + 归档完成不扣减")
def test_archive_decrements_workload(builder, techs):
    """全链路：派工 +1 → 接单保持 → 归档后回退"""
    a = techs["a"]["id"]
    base = workload_of(a)
    wo = builder.to("ARCHIVING", case="workload-archive", technician_id=a)
    assert workload_of(a) == base + 1, "待归档时工作量仍应 +1"
    builder.fill_fields(wo["id"])
    st, body = builder.api.post(f"/work-orders/{wo['id']}/archive-complete", builder.admin)
    assert st == 200, body
    assert workload_of(a) == base, f"归档后应回到 {base}，实际 {workload_of(a)}"

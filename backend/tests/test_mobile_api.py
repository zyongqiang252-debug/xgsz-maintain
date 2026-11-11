# -*- coding: utf-8 -*-
"""移动端接口（/m/v1）与 5 个硬伤回归

对应《移动端功能扩展清单》批次一：
- H1 队列不再漏单（ACCEPTED / 工单池可见）
- H2 状态推进走统一状态机（进度时间线不再缺节点）
- H3 完成进 ARCHIVING、写 resolved_at
- H4 上报复用 PC 建单（created_by / 分类 / SLA）
- H5 真上传（upload 接口可用，附件落到 fault_media / attachments）
"""
from conftest import db, progress_log_count, PREFIX, RUN


def test_queue_covers_accepted_and_pool(api, techs, builder):
    """H1：处理中 tab 能看到 ACCEPTED 工单；工单池数量/条目独立返回"""
    wo = builder.to("ACCEPTED", case="mob-queue", technician_id=techs["a"]["id"])
    token = techs["a"]["token"]

    st, q = api.get("/m/v1/queue", token, params={"tab": "processing", "page_size": 50})
    assert st == 200, q
    assert q["counts"]["processing"] >= 1
    assert any(i["id"] == wo["id"] for i in q["items"]), "ACCEPTED 工单不在处理中队列里"

    st, pool = api.get("/m/v1/queue", token, params={"tab": "pool", "page_size": 5})
    assert st == 200
    assert "pool_count" in pool and "counts" in pool
    assert pool["total"] == pool["counts"]["pool"]


def test_mobile_report_uses_pc_create(api, techs):
    """H4：移动端上报 → created_by / 故障分类 / SLA 截止都由 PC 建单逻辑补齐"""
    st, body = api.post("/m/v1/report", techs["a"]["token"], json={
        "device_code": "PYTEST-MOB-01",
        "fault_description": f"{PREFIX}移动端上报 {RUN}",
        "media": [],
        "location": "测试机房",
    })
    assert st == 200, body
    wid = body["work_order_id"]
    assert body["status"] == "ACCEPTED", "技术员自建单应自动接单，而不是掉进工单池"

    s = db()
    try:
        from app.models.work_order import WorkOrder
        w = s.query(WorkOrder).filter(WorkOrder.id == wid).first()
        assert w is not None
        assert w.created_by == techs["a"]["id"], "created_by 没写，PC 端按建单人查不到"
        assert w.fault_category, "故障分类没自动归类"
        assert w.resolve_due_at is not None, "SLA 截止时间没算"
        assert w.alert_level, "告警级别没推导"
    finally:
        s.close()


def test_mobile_complete_goes_archiving(api, techs, builder):
    """H3：移动端完成 → ARCHIVING、resolved_at 有值、进度日志有记录"""
    wo = builder.to("IN_PROGRESS", case="mob-complete", technician_id=techs["a"]["id"])
    wid = wo["id"]
    before = progress_log_count(wid)

    st, body = api.post(f"/m/v1/wo/{wid}/complete", techs["a"]["token"], json={
        "work_hours": 0.5,
        "solution_desc": f"{PREFIX}移动端完成 {RUN}",
        "repair_result": "PERMANENT_FIX",
    })
    assert st == 200, body
    assert body["status"] == "ARCHIVING"

    s = db()
    try:
        from app.models.work_order import WorkOrder
        w = s.query(WorkOrder).filter(WorkOrder.id == wid).first()
        assert w.status.value == "ARCHIVING"
        assert w.resolved_at is not None, "resolved_at 没写，SLA 修复时长算不出来"
        assert w.end_time is not None
    finally:
        s.close()
    assert progress_log_count(wid) > before, "完成没有写进度日志"

# -*- coding: utf-8 -*-
"""并发：客户门户报修不能撞单号、不能 500

C-04：工单号原本是「查当天最大值 + 1」先查后插，无幂等键；
10 个请求同时进来应全部成功且工单号唯一（或靠唯一约束返回可读错误，而不是 500）。
"""
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests

import uuid

from conftest import API, PREFIX, RUN, purge_orders


def _make_customer_with_device(api, admin):
    tag = uuid.uuid4().hex[:6]
    st, cust = api.post("/customers/", admin, json={
        "name": f"{PREFIX}并发客户{RUN}-{tag}",
        "phone": "13" + f"{int(uuid.uuid4().hex[:9], 16) % 10**9:09d}",
        "password": "Concurrent1",
    })
    assert st in (200, 201), f"建客户失败：{cust}"
    st, dev = api.post("/devices/", admin, json={
        "device_code": f"{PREFIX}并发设备{RUN}-{tag}",
        "device_name": f"{PREFIX}并发设备{RUN}-{tag}",
    })
    assert st in (200, 201), f"建设备失败：{dev}"
    st, _ = api.put(f"/customers/{cust['id']}/devices", admin, json={"device_ids": [dev["id"]]})
    assert st == 200
    st, body = api.post("/customer/login", json={"phone": cust["phone"], "password": "Concurrent1"})
    assert st == 200 and body.get("token"), f"客户登录失败：{body}"
    return cust, dev, body["token"]


@pytest.mark.xfail(strict=True, reason="C-04 已知缺陷：并发报修撞工单号，10 并发里 6 个 500")
def test_concurrent_customer_reports(api, admin):
    cust, dev, token = _make_customer_with_device(api, admin)

    def report(i):
        r = requests.post(
            API + "/customer/reports",
            headers={"Authorization": f"Bearer {token}"},
            json={"device_id": dev["id"], "fault_description": f"{PREFIX}并发报修 {RUN}-{i}"},
            timeout=60,
        )
        try:
            body = r.json()
        except Exception:
            body = {}
        return r.status_code, body.get("work_order_no") or body.get("id"), body.get("detail", "")

    with ThreadPoolExecutor(max_workers=10) as ex:
        results = list(ex.map(report, range(10)))

    codes = {}
    for st, _, _ in results:
        codes[st] = codes.get(st, 0) + 1
    nos = [no for st, no, _ in results if st == 200 and no]
    errors = [d for st, _, d in results if st != 200]

    assert codes.get(500, 0) == 0, f"并发出现 500：状态分布 {codes}，错误示例 {errors[:3]}"
    assert codes.get(200, 0) == 10, f"应 10 个请求全部成功，实际 {codes}"
    assert len(set(nos)) == 10, f"工单号撞车：{len(set(nos))} 个唯一 / 10 个"


def test_same_customer_report_with_same_content_twice(api, admin):
    """同一客户连报两条相同内容：不应去重（业务上可能是两次独立故障），但必须两条不同单号"""
    cust, dev, token = _make_customer_with_device(api, admin)
    payload = {"device_id": dev["id"], "fault_description": f"{PREFIX}重复报修 {RUN}"}
    st1, b1 = api.post("/customer/reports", token, json=payload)
    st2, b2 = api.post("/customer/reports", token, json=payload)
    assert (st1, st2) == (200, 200), (st1, st2, b1, b2)
    no1 = b1.get("work_order_no") or b1.get("id")
    no2 = b2.get("work_order_no") or b2.get("id")
    assert no1 != no2, f"两次报修拿到同一个工单号：{no1}"
    purge_orders()

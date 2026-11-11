# -*- coding: utf-8 -*-
r"""xgsz-maintain 全模块联动测试（管理员 / 技术员 / 客户三个身份）

覆盖：用户增删改与权限、客户 360（联系人/站点/设备/门户报修）、设备增删、
备件与仓储（SN 逐件、出入库、流水、领用申请-审批-发料、盘点、预警、实例生命周期）、
工单全生命周期（提交→派工→接单→到场→检查→维修→挂起/恢复→领用→完成→归档校验→归档）、
客户验收/评价、通知、驾驶舱统计、以及反向删除的约束行为。

用法（backend 目录下，带 PYTHONPATH）：
    cd backend
    .\.venv\Scripts\python.exe ..\tools\e2e_linkage_test.py            # 跑完清理
    .\.venv\Scripts\python.exe ..\tools\e2e_linkage_test.py --keep     # 保留数据便于排查
产物：%TEMP%/xgsz-e2e-report.json
"""
import argparse
import json
import os
import random
import string
import sys
import tempfile
import time
from datetime import datetime

import requests

BASE = os.environ.get("XGSZ_BASE", "http://127.0.0.1:18080")
API = BASE + "/api/v1"
RUN = datetime.now().strftime("%m%d%H%M%S")
REPORT_PATH = os.path.join(tempfile.gettempdir(), "xgsz-e2e-report.json")

S = requests.Session()
RESULTS = []
IDS = {
    "users": [], "customers": [], "devices": [], "parts": [], "warehouses": [],
    "work_orders": [], "requisitions": [], "stocktakes": [], "instances": [],
}


def check(name, ok, detail=""):
    RESULTS.append({"name": name, "ok": bool(ok), "kind": "pass" if ok else "fail", "detail": str(detail)[:600]})
    print(("[PASS] " if ok else "[FAIL] ") + name + ("  " + str(detail)[:300] if detail else ""))


def gap(name, detail=""):
    """产品缺陷/行为缺口：不算脚本失败，单独计数，便于汇总给开发"""
    RESULTS.append({"name": name, "ok": True, "kind": "gap", "detail": str(detail)[:600]})
    print("[GAP ] " + name + ("  " + str(detail)[:300] if detail else ""))


def api(method, path, token=None, expect=None, **kw):
    headers = kw.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = path if path.startswith("http") else API + path
    try:
        r = S.request(method, url, headers=headers, timeout=kw.pop("timeout", 120), **kw)
    except Exception as e:
        return 0, {"error": str(e)}
    try:
        body = r.json()
    except Exception:
        body = {"_text": (r.text or "")[:300]}
    if expect is not None and r.status_code not in (expect if isinstance(expect, (list, tuple, set)) else [expect]):
        check(f"!! 期望 {expect} 实际 {r.status_code}：{method} {path}", False, body)
    return r.status_code, body


def login(username, password):
    st, body = api("POST", "/auth/login-by-password", json={"username": username, "password": password})
    return (body.get("token") or body.get("access_token")), body, st


def rand_phone():
    return "139" + "".join(random.choice(string.digits) for _ in range(8))


def main(keep=False):
    admin_token = None
    tech_token = None
    customer_token = None
    tech_user = None
    cust = None
    device = None
    part_a = part_b = wh = loc = None
    wo = None

    # ================= 0. 基础 =================
    if not keep:
        db_cleanup(broad=True)   # 清掉上次崩溃留下的 E2E 残留
    st, h = api("GET", BASE + "/health")
    check("0-1 健康检查", st == 200 and h.get("database") == "connected", h)
    admin_token, admin_body, st = login("admin", "admin123")
    check("0-2 管理员登录", st == 200 and bool(admin_token), admin_body.get("role"))
    st, me = api("GET", "/users/me", admin_token)
    check("0-3 当前用户 /users/me", st == 200 and me.get("username") == "admin", me.get("role"))
    st, wrong = api("POST", "/auth/login-by-password", json={"username": "admin", "password": "wrong-pass"})
    check("0-4 错误密码应被拒", st in (400, 401), f"status={st}")

    def part_stock(pid):
        """从列表接口读库存（列表不缓存；详情有 300s 缓存，不能用来断言）"""
        _, lst = api("GET", "/spare-parts/", admin_token, params={"page_size": 100})
        for it in (lst.get("items") or []):
            if it.get("id") == pid:
                return float(it.get("stock_quantity") or 0), float(it.get("reserved_quantity") or 0)
        return None, None

    # ================= 1. 用户模块 =================
    tech_name = f"e2e_tech_{RUN}"
    st, tech_user = api("POST", "/users/", admin_token, json={
        "username": tech_name, "password": "E2ePass123", "real_name": f"E2E技术员{RUN}",
        "role": "TECHNICIAN", "phone": rand_phone(), "department": "维修部",
    })
    if st == 400:
        tech_name = f"e2e_tech_{RUN}_{random.randint(100, 999)}"
        st, tech_user = api("POST", "/users/", admin_token, json={
            "username": tech_name, "password": "E2ePass123", "real_name": f"E2E技术员{RUN}",
            "role": "TECHNICIAN", "phone": rand_phone(), "department": "维修部",
        })
    check("1-1 管理员创建技术员", st in (200, 201), f"status={st} {tech_user}")
    if isinstance(tech_user, dict) and tech_user.get("id"):
        IDS["users"].append(tech_user["id"])
    tech_token, tech_body, st = login(tech_name, "E2ePass123")
    st, tech2 = api("POST", "/users/", admin_token, json={
        "username": f"e2e_tech2_{RUN}", "password": "E2ePass123",
        "real_name": f"E2E技术员2{RUN}", "role": "TECHNICIAN", "phone": rand_phone()})
    if isinstance(tech2, dict) and tech2.get("id"):
        IDS["users"].append(tech2["id"])
    else:
        tech2 = {"id": tech_user.get("id")}
    check("1-2 新用户可登录", st == 200 and bool(tech_token), tech_body.get("role"))
    st, dup = api("POST", "/users/", admin_token, json={"username": tech_name, "password": "x123456", "real_name": "重复"})
    check("1-3 重复用户名被拒", st in (400, 409), f"status={st}")
    st, created = api("POST", "/users/", tech_token, json={
        "username": f"e2e_deny_{RUN}", "password": "E2ePass123", "real_name": "越权"})
    check("1-4 技术员建用户应 403", st == 403, f"status={st}")
    st, upd = api("PUT", f"/users/{tech_user['id']}", admin_token, json={"phone": rand_phone(), "role": "TECHNICIAN"})
    st2, u2 = api("GET", f"/users/{tech_user['id']}", admin_token)
    check("1-5 管理员更新用户资料", st == 200 and u2.get("phone") == upd.get("phone"), f"{st}/{u2.get('phone')}")
    st, selfupd = api("PUT", f"/users/{tech_user['id']}", tech_token, json={"phone": rand_phone()})
    check("1-6 技术员改自己资料", st == 200, f"status={st}")
    st, _ = api("DELETE", f"/users/{tech_user['id']}", tech_token)
    check("1-7 技术员删用户应 403", st == 403, f"status={st}")
    st, dis = api("PUT", f"/users/{tech_user['id']}", admin_token, json={"is_active": False})
    st2, _, st3 = login(tech_name, "E2ePass123")
    check("1-8 禁用后无法登录", st == 200 and st3 in (400, 401, 403), f"禁用={st} 登录={st3}")
    st, _ = api("PUT", f"/users/{tech_user['id']}", admin_token, json={"is_active": True})
    tech_token, _, st = login(tech_name, "E2ePass123")
    check("1-9 重新启用后可登录", st == 200 and bool(tech_token), f"status={st}")
    st, logs = api("GET", "/users/login-logs", admin_token, params={"limit": 20})
    check("1-10 登录审计有记录", st == 200 and (logs.get("total", 0) > 0 or logs.get("items")), f"total={logs.get('total')}")

    # ================= 2. 仓储 / 备件 =================
    st, wh = api("POST", "/warehouses/", admin_token, json={
        "code": f"E2E-WH-{RUN}", "name": f"E2E测试仓{RUN}", "address": "自检地址"})
    check("2-1 管理员建仓库", st in (200, 201), f"status={st}")
    if isinstance(wh, dict) and wh.get("id"):
        IDS["warehouses"].append(wh["id"])
    st, loc = api("POST", f"/warehouses/{wh['id']}/locations", admin_token,
                  json={"code": "A-01", "name": "A架1层", "rack": "A"})
    check("2-2 建库位", st in (200, 201), f"status={st}")
    st, _ = api("POST", "/warehouses/", tech_token, json={"code": f"E2E-WHX-{RUN}", "name": "越权仓"})
    check("2-3 技术员建仓应 403", st == 403, f"status={st}")

    st, part_a = api("POST", "/spare-parts/", admin_token, json={
        "part_code": f"E2E-GPU-A-{RUN}", "part_name": f"E2E GPU 卡{RUN}", "unit": "个",
        "stock_quantity": 0, "safety_stock": 2, "unit_price": 1000.0,
        "warehouse_id": wh["id"], "need_sn": True, "location": "A-01"})
    check("2-4 建需SN备件", st in (200, 201), f"status={st}")
    if isinstance(part_a, dict) and part_a.get("id"):
        IDS["parts"].append(part_a["id"])
    st, part_b = api("POST", "/spare-parts/", admin_token, json={
        "part_code": f"E2E-FAN-B-{RUN}", "part_name": f"E2E 风扇{RUN}", "unit": "个",
        "stock_quantity": 0, "safety_stock": 1, "unit_price": 50.0,
        "warehouse_id": wh["id"], "need_sn": False})
    check("2-5 建普通备件", st in (200, 201), f"status={st}")
    if isinstance(part_b, dict) and part_b.get("id"):
        IDS["parts"].append(part_b["id"])
    st, _ = api("POST", "/spare-parts/", tech_token, json={
        "part_code": f"E2E-DENY-{RUN}", "part_name": "越权件"})
    check("2-6 技术员建备件应 403", st == 403, f"status={st}")

    # 入库 2 件（带 SN）
    sn1, sn2 = f"SN-{RUN}-01", f"SN-{RUN}-02"
    st, inb = api("POST", f"/spare-parts/{part_a['id']}/stock-in", admin_token,
                  json={"quantity": 2, "serial_no": f"{sn1},{sn2}", "unit_price": 1000.0, "remark": "E2E 入库"})
    check("2-7 入库2件带SN", st == 200, f"status={st} {inb.get('message', '')}")
    st, pa = api("GET", f"/spare-parts/{part_a['id']}", admin_token)
    check("2-8 入库后库存=2", st == 200 and float(pa.get("stock_quantity") or 0) == 2, pa.get("stock_quantity"))
    st, insts = api("GET", "/part-instances/", admin_token, params={"part_id": part_a["id"], "page_size": 50})
    items = insts.get("items", []) if isinstance(insts, dict) else []
    IDS["instances"] += [i["id"] for i in items if i.get("id")]
    check("2-9 按SN生成2个实例", len([i for i in items if i.get("sn") in (sn1, sn2)]) == 2,
          f"实例数={len(items)} SN={[i.get('sn') for i in items]}")
    st, mv = api("GET", "/spare-parts/movements", admin_token, params={"part_id": part_a["id"], "page_size": 20})
    mv_items = mv.get("items", []) if isinstance(mv, dict) else []
    check("2-10 入库写流水", st == 200 and len(mv_items) >= 1,
          [f"{m.get('movement_type')}:{m.get('quantity')}" for m in mv_items])

    # 库存不足：出库超过库存
    st, over = api("POST", f"/spare-parts/{part_a['id']}/consume", admin_token, json={"quantity": 5})
    check("2-11 出库超库存被拒", st == 400, f"status={st} {over.get('detail', '')}")

    # ================= 3. 客户 360 =================
    phone = rand_phone()
    st, cust = api("POST", "/customers/", admin_token, json={
        "name": f"E2E客户{RUN}", "phone": phone, "password": "CustPass123",
        "company": f"E2E科技有限公司{RUN}", "address": "测试市测试路1号",
        "level": "VIP", "tags": ["E2E", "GPU"], "sla_response_hours": 4, "sla_resolve_hours": 24,
    })
    check("3-1 建客户", st in (200, 201), f"status={st} {cust.get('detail', '')}")
    if isinstance(cust, dict) and cust.get("id"):
        IDS["customers"].append(cust["id"])
    st, ct = api("POST", f"/customers/{cust['id']}/contacts", admin_token,
                 json={"name": "张三", "phone": rand_phone(), "title": "IT经理", "is_primary": True})
    check("3-2 加联系人", st in (200, 201), f"status={st}")
    st, site = api("POST", f"/customers/{cust['id']}/sites", admin_token,
                   json={"name": "E2E机房", "address": "测试市机房路9号", "is_default": True})
    check("3-3 加机房站点", st in (200, 201), f"status={st}")
    st, clogin = api("POST", "/customer/login", json={"phone": phone, "password": "CustPass123"})
    customer_token = clogin.get("token") if isinstance(clogin, dict) else None
    check("3-4 客户门户登录", st == 200 and bool(customer_token), f"status={st}")
    st, cupd = api("PUT", f"/customers/{cust['id']}", admin_token, json={
        "name": cust["name"], "phone": phone, "company": cust["company"],
        "address": cust["address"], "level": "KEY", "remark": "E2E 更新备注"})
    check("3-5 更新客户", st == 200 and cupd.get("level") == "KEY", f"status={st} level={cupd.get('level')}")
    st, c360 = api("GET", f"/customers/{cust['id']}", admin_token)
    check("3-6 客户详情含级别/SLA", st == 200 and c360.get("level") in ("KEY", "VIP")
          and "sla_response_hours" in c360,
          f"level={c360.get('level')} sla字段={c360.get('sla_response_hours')}")

    # ================= 4. 设备 + 绑定客户 =================
    st, device = api("POST", "/devices/", admin_token, json={
        "device_code": f"E2E-GPU-{RUN}", "device_name": f"E2E GPU服务器{RUN}",
        "device_type": "GPU服务器", "model": "NF5688M6", "serial_no": f"DEV-{RUN}",
        "location": "E2E机房A区", "gpu_model": "H800", "gpu_count": 8,
    })
    check("4-1 建设备", st in (200, 201), f"status={st} {device.get('detail', '')}")
    if isinstance(device, dict) and device.get("id"):
        IDS["devices"].append(device["id"])
    st, bind = api("PUT", f"/customers/{cust['id']}/devices", admin_token,
                   json={"device_ids": [device["id"]]})
    check("4-2 设备绑定到客户", st == 200, f"status={st}")
    st, mydev = api("GET", "/customer/devices", customer_token)
    dev_items = mydev.get("items") if isinstance(mydev, dict) else mydev
    check("4-3 客户门户可见设备", st == 200 and any(
        str(d.get("device_code")) == device.get("device_code") for d in (dev_items or [])),
        f"status={st} 数量={len(dev_items or [])}")

    # ================= 5. 工单全生命周期 =================
    st, wo = api("POST", "/work-orders/", admin_token, json={
        "device_id": device["id"], "device_code": device["device_code"],
        "fault_description": f"E2E 自检：GPU 掉卡 Xid 79（{RUN}）",
        "fault_phenomenon": "nvidia-smi 少卡", "priority": "P2",
        "location": "E2E机房A区", "reporter_id": None,
    })
    check("5-1 建工单(草稿)", st in (200, 201), f"status={st} {wo.get('detail', '')}")
    if isinstance(wo, dict) and wo.get("id"):
        IDS["work_orders"].append(wo["id"])
    wo_id = wo["id"]
    if wo.get("customer_name") or wo.get("customer_id"):
        check("5-2 工单继承客户快照", True, f"customer={wo.get('customer_name')}")
    else:
        gap("5-2 管理员建单无法关联客户", "WorkOrderCreate 没有 customer_id 字段，管理端建单 customer=None；"
            "只有客户门户报修才会写 customer_id，导致客户 360 的工单历史漏单")

    def transit(to, token=admin_token, **extra):
        body = {"to_status": to, **extra}
        return api("POST", f"/work-orders/{wo_id}/transition", token, json=body)

    st, r = transit("SUBMITTED", remark="E2E 提交")
    check("5-3 提交报修 SUBMITTED", st == 200 and r.get("status") == "SUBMITTED", f"status={st} {r.get('status')}")
    st, bad = transit("ARCHIVED")
    check("5-4 非法流转被拒", st == 400, f"status={st} {bad.get('detail', '')}")
    st, r = transit("ASSIGNED", technician_id=tech_user["id"], remark="E2E 派工")
    check("5-7 派工 ASSIGNED", st == 200 and r.get("status") == "ASSIGNED",
          f"status={st} tech={r.get('technician_name')}")
    st, r = transit("ACCEPTED", token=tech_token)
    check("5-8 技术员接单", st == 200, f"status={st} {r.get('status')}")
    st, r = transit("ARRIVED", token=tech_token)
    check("5-9 到场 ARRIVED", st == 200, f"status={st}")
    st, r = transit("INSPECTING", token=tech_token)
    check("5-10 检查 INSPECTING", st == 200, f"status={st}")
    st, r = transit("IN_PROGRESS", token=tech_token)
    check("5-11 维修中 IN_PROGRESS", st == 200, f"status={st}")
    st, r = transit("ACCEPTED", token=tech_token)
    check("5-12 逆向流转被拒", st == 400, f"status={st}")
    # 挂起/恢复：只有 已接单/已到场/检查中/维修中 允许
    st, r = api("POST", f"/work-orders/{wo_id}/hold", tech_token,
                json={"reason": "VENDOR", "remark": "E2E 等厂商"})
    check("5-5 挂起工单", st == 200, f"status={st} {r.get('detail', '')}")
    st, r = api("POST", f"/work-orders/{wo_id}/resume", tech_token)
    check("5-6 恢复工单", st == 200, f"status={st} {r.get('detail', '')}")

    # ---- 领用申请：技术员申请 → 技术员审批被拒 → 管理员审批 → 发料 ----
    st, req = api("POST", "/spare-parts/requisitions/", tech_token, json={
        "part_id": part_a["id"], "quantity": 1, "work_order_id": wo_id, "reason": "E2E 换卡"})
    check("5-13 技术员提领用申请", st in (200, 201), f"status={st} {req.get('detail', '')}")
    if isinstance(req, dict) and req.get("id"):
        IDS["requisitions"].append(req["id"])
    rid = req["id"]
    st, _ = api("POST", f"/spare-parts/requisitions/{rid}/approve", tech_token)
    check("5-14 技术员审批应 403", st == 403, f"status={st}")
    st, appr = api("POST", f"/spare-parts/requisitions/{rid}/approve", admin_token)
    check("5-15 管理员审批通过(预占)", st == 200 and appr.get("status") == "APPROVED",
          f"status={st} 预占={appr.get('reserved_quantity')}")
    stk16, rsv16 = part_stock(part_a["id"])
    check("5-16 审批后库存未扣、预占+1", stk16 == 2 and rsv16 == 1,
          f"stock={stk16} reserved={rsv16}（审批响应预占={appr.get('reserved_quantity')}）")
    st, _ = api("POST", f"/spare-parts/requisitions/{rid}/issue", tech_token, json={"remark": "越权发料"})
    check("5-17 技术员发料应 403", st == 403, f"status={st}")
    st, iss = api("POST", f"/spare-parts/requisitions/{rid}/issue", admin_token, json={"remark": "E2E 发料"})
    check("5-18 管理员发料成功", st == 200 and iss.get("status") == "ISSUED", f"status={st} {iss.get('status')}")

    st, pa3 = api("GET", f"/spare-parts/{part_a['id']}", admin_token)
    stk, rsv = part_stock(part_a["id"])
    check("5-19 发料后库存-1、预占释放", stk == 1 and rsv == 0, f"stock={stk} reserved={rsv}")
    if float(pa3.get("stock_quantity") or 0) != stk or float(pa3.get("reserved_quantity") or 0) != rsv:
        gap("5-19b 备件详情缓存未失效", f"详情接口仍返回 stock={pa3.get('stock_quantity')} "
            f"reserved={pa3.get('reserved_quantity')}，实际 stock={stk} reserved={rsv}；"
            "出库/领用只清了 stock_alerts 缓存，spare_part:{id} 有 300s TTL")
    st, wo_det = api("GET", f"/work-orders/{wo_id}", admin_token)
    used = wo_det.get("used_parts") or []
    check("5-20 工单备件与成本回写",
          any((u.get("code") or u.get("part_code")) == part_a["part_code"] for u in used),
          f"used={used} cost={wo_det.get('total_cost') or wo_det.get('cost')}")
    st, insts2 = api("GET", "/part-instances/", admin_token, params={"part_id": part_a["id"], "page_size": 50})
    issued = [i for i in (insts2.get("items") or []) if i.get("status") in ("INSTALLED", "ISSUED")]
    check("5-21 发料后实例状态流转", len(issued) == 1,
          [(i.get("sn"), i.get("status"), i.get("device_code")) for i in issued])

    # ---- 维修填写 + 列表页「维修完成」→ 待归档 → 归档校验 → 归档 ----
    st, upd = api("PUT", f"/work-orders/{wo_id}", tech_token, json={
        "root_cause": "GPU 卡故障", "root_cause_category": "硬件",
        "solution_steps": "1. 停机 2. 更换 GPU 3. 压测", "repair_result": "已修复",
        "work_hours": 2.5})
    check("5-22 技术员填维修信息", st == 200, f"status={st}")
    st, r = transit("ARCHIVING", token=tech_token, remark="E2E 维修完成")
    check("5-23 维修完成→待归档 ARCHIVING", st == 200 and r.get("status") == "ARCHIVING",
          f"status={st} {r.get('status') or r.get('detail')}")
    st, chk = api("POST", f"/work-orders/{wo_id}/archive-check", admin_token)
    check("5-24 归档校验返回齐全性", st == 200 and "completeness" in chk,
          f"passed={chk.get('passed')} completeness={chk.get('completeness')} missing={chk.get('missing_fields')}")
    if not chk.get("passed"):
        api("PUT", f"/work-orders/{wo_id}", admin_token,
            json={"fault_phenomenon": "nvidia-smi 少卡", "fault_description": f"E2E 自检：GPU 掉卡 Xid 79（{RUN}）"})
        st, chk = api("POST", f"/work-orders/{wo_id}/archive-check", admin_token)
    st, arch = api("POST", f"/work-orders/{wo_id}/archive-complete", admin_token)
    st, wo_det3 = api("GET", f"/work-orders/{wo_id}", admin_token)
    check("5-25 归档完成 ARCHIVED", st == 200 and wo_det3.get("status") == "ARCHIVED",
          f"status={wo_det3.get('status')} detail={arch.get('detail', '')} missing={chk.get('missing_fields')}")
    st, logs = api("GET", f"/work-orders/{wo_id}/progress", admin_token)
    log_items = logs.get("progress_logs") if isinstance(logs, dict) else logs
    check("5-26 进度日志全链路留痕", st == 200 and len(log_items or []) >= 7,
          f"日志数={len(log_items or [])} 链路={[l.get('to_status') for l in (log_items or [])]}")
    st, pdf = api("GET", f"/work-orders/{wo_id}/pdf", admin_token)
    check("5-27 工单PDF可下载", st == 200, f"status={st}")
    st, el = api("GET", f"/work-orders/{wo_id}/edit-logs", admin_token)
    check("5-28 编辑日志有记录", st == 200, f"status={st}")

    # ---- 通知 ----
    st, nt = api("GET", "/notifications/", tech_token, params={"page_size": 20})
    nt_items = nt.get("items") if isinstance(nt, dict) else nt
    check("5-29 技术员收到派工/领用通知", st == 200 and len(nt_items or []) > 0,
          f"数量={len(nt_items or [])}")
    st, uc = api("GET", "/notifications/unread-count", tech_token)
    check("5-30 未读数接口", st == 200, uc)

    # ---- 详情页「提交完成」路径（/complete）：COMPLETED 之后还能不能归档 ----
    st, wo2 = api("POST", "/work-orders/", admin_token, json={
        "device_id": device["id"], "device_code": device["device_code"],
        "fault_description": f"E2E 分支B：提交完成路径（{RUN}）", "priority": "P3"})
    wo2_id = wo2.get("id") if isinstance(wo2, dict) else None
    if wo2_id:
        IDS["work_orders"].append(wo2_id)
        for to in ("SUBMITTED", "ASSIGNED"):
            api("POST", f"/work-orders/{wo2_id}/transition", admin_token,
                json={"to_status": to, "technician_id": tech_user["id"] if to == "ASSIGNED" else None})
        for to in ("ACCEPTED", "ARRIVED", "INSPECTING", "IN_PROGRESS"):
            api("POST", f"/work-orders/{wo2_id}/transition", tech_token, json={"to_status": to})
        api("PUT", f"/work-orders/{wo2_id}", tech_token,
            json={"root_cause": "线缆松动", "solution_steps": "重插", "repair_result": "已修复", "work_hours": 1})
        st, comp = api("POST", f"/work-orders/{wo2_id}/complete", tech_token)
        _, wo2_det = api("GET", f"/work-orders/{wo2_id}", admin_token)
        check("5-31 /complete 返回 COMPLETED", wo2_det.get("status") == "COMPLETED",
              f"status={wo2_det.get('status')} {comp.get('knowledge_synced')}")
        st, chk2 = api("POST", f"/work-orders/{wo2_id}/archive-check", admin_token)
        st, arch2 = api("POST", f"/work-orders/{wo2_id}/archive-complete", admin_token)
        if st != 200:
            gap("5-32 COMPLETED 是死状态", f"详情页提交完成后状态为 COMPLETED，但归档完成要求 ARCHIVING → {st} "
                f"{arch2.get('detail', '')}；前端把 COMPLETED 显示成「待归档」却点不了归档按钮")

    # ================= 6. 客户门户报修 → 派工维修 → 验收 → 评价 =================
    st, rep = api("POST", "/customer/reports", customer_token, json={
        "device_id": device["id"], "site_id": site.get("id") if isinstance(site, dict) else None,
        "fault_description": f"E2E 客户报修：风扇异响（{RUN}）", "contact_name": "张三"})
    check("6-1 客户门户提交报修", st in (200, 201), f"status={st} {rep.get('detail', '')}")
    rep_id = rep.get("id") or rep.get("work_order_id")
    if rep_id:
        IDS["work_orders"].append(rep_id)
    st, myrep = api("GET", "/customer/reports", customer_token)
    check("6-2 客户可查自己的报修", st == 200, f"status={st}")
    if rep_id:
        _, rd = api("GET", f"/work-orders/{rep_id}", admin_token)
        check("6-2b 客户报修带客户快照", bool(rd.get("customer_id")), f"customer_id={rd.get('customer_id')}")
        for to, tk in (("ASSIGNED", admin_token), ("ACCEPTED", tech_token), ("ARRIVED", tech_token),
                       ("INSPECTING", tech_token), ("IN_PROGRESS", tech_token), ("ARCHIVING", tech_token)):
            body = {"to_status": to}
            if to == "ASSIGNED":
                body["technician_id"] = tech_user["id"]
            api("POST", f"/work-orders/{rep_id}/transition", tk, json=body)
        st, acc = api("POST", f"/customer/reports/{rep_id}/accept", customer_token,
                      json={"accepted": True, "remark": "E2E 客户验收"})
        check("6-3 客户在待归档阶段验收", st == 200, f"status={st} {acc.get('detail', '')}")
        st, chk3 = api("POST", f"/work-orders/{rep_id}/archive-check", admin_token)
        if not chk3.get("passed"):
            api("PUT", f"/work-orders/{rep_id}", admin_token, json={
                "fault_phenomenon": "风扇异响", "root_cause": "轴承磨损",
                "solution_steps": "更换风扇", "repair_result": "已修复", "work_hours": 1.5})
            api("POST", f"/work-orders/{rep_id}/archive-check", admin_token)
        st, arch3 = api("POST", f"/work-orders/{rep_id}/archive-complete", admin_token)
        _, rd3 = api("GET", f"/work-orders/{rep_id}", admin_token)
        check("6-3b 客户工单归档", st == 200 and rd3.get("status") == "ARCHIVED",
              f"status={rd3.get('status')} {arch3.get('detail', '')}")
        st, rate = api("POST", f"/customer/reports/{rep_id}/rating", customer_token,
                       json={"score": 5, "comment": "E2E 好评"})
        check("6-4 客户评价(需已归档)", st == 200, f"status={st} {rate.get('detail', '')}")

    # ================= 7. 库存联动：直接出库 / 预警 / 盘点 =================
    st, cons = api("POST", f"/spare-parts/{part_a['id']}/consume", tech_token,
                   json={"quantity": 1, "serial_no": sn2, "remark": "E2E 技术员直接出库"})
    check("7-1 技术员直接出库(带SN)", st == 200, f"status={st} {cons.get('detail', '')}")
    st, pa4 = api("GET", f"/spare-parts/{part_a['id']}", admin_token)
    check("7-2 出库后库存=0", float(pa4.get("stock_quantity") or 0) == 0, pa4.get("stock_quantity"))
    st, al = api("GET", "/spare-parts/alerts", admin_token)
    al_text = json.dumps(al, ensure_ascii=False)
    check("7-3 跌破安全库存进预警", st == 200 and (part_a["part_code"] in al_text),
          f"status={st} alerts={al_text[:200]}")
    st, same_sn = api("POST", f"/spare-parts/{part_a['id']}/consume", tech_token,
                      json={"quantity": 1, "serial_no": sn2, "remark": "重复SN"})
    check("7-4 同一SN重复出库被拒", st == 400, f"status={st} {same_sn.get('detail', '')}")

    # 盘点：先给 B 入 3 件
    api("POST", f"/spare-parts/{part_b['id']}/stock-in", admin_token, json={"quantity": 3, "remark": "E2E 入库"})
    st, take = api("POST", "/stocktakes/", admin_token, json={"warehouse_id": wh["id"], "remark": f"E2E 盘点{RUN}"})
    check("7-5 建盘点单(生成快照)", st in (200, 201), f"status={st} {take.get('detail', '')}")
    if isinstance(take, dict) and take.get("id"):
        IDS["stocktakes"].append(take["id"])
    st, tdet = api("GET", f"/stocktakes/{take['id']}", admin_token)
    items = (tdet.get("items") if isinstance(tdet, dict) else []) or []
    target = next((i for i in items if i.get("part_code") == part_b["part_code"]), None)
    check("7-6 盘点明细含测试仓备件", st == 200 and target is not None, f"明细={len(items)}")
    if target:
        # 盘点要求全部录完：其余明细按当前库存照实盘
        count_items = []
        for it in items:
            if it.get("part_code") == part_b["part_code"]:
                count_items.append({"item_id": it["id"], "actual_qty": 2, "reason": "E2E 盘亏1件"})
            else:
                count_items.append({"item_id": it["id"],
                                    "actual_qty": float(it.get("system_qty") or 0)})
        st, cnt = api("POST", f"/stocktakes/{take['id']}/count", tech_token, json={"items": count_items})
        check("7-7 技术员录实盘(全部明细)", st == 200, f"status={st} {cnt.get('detail', '')}")
        st, sub = api("POST", f"/stocktakes/{take['id']}/submit", tech_token)
        check("7-8 提交盘点", st == 200, f"status={st} {sub.get('detail', '')}")
        st, _ = api("POST", f"/stocktakes/{take['id']}/approve", tech_token, json={})
        check("7-9 技术员审批盘点应 403", st == 403, f"status={st}")
        st, ap = api("POST", f"/stocktakes/{take['id']}/approve", admin_token, json={"remark": "E2E 审批"})
        check("7-10 管理员审批盘点", st == 200, f"status={st} {ap.get('detail', '')}")
        stk_b, _ = part_stock(part_b["id"])
        check("7-11 盘亏后库存=2", stk_b == 2, f"stock={stk_b}")

    # ================= 8. 备件实例生命周期 =================
    st, inst = api("POST", "/part-instances/", admin_token, json={
        "part_id": part_b["id"], "serial_no": f"SN-B-{RUN}", "status": "IN_STOCK",
        "warehouse_id": wh["id"]})
    check("8-1 手工登记实例", st in (200, 201), f"status={st} {inst.get('detail', '')}")
    iid = inst.get("id") if isinstance(inst, dict) else None
    if iid:
        IDS["instances"].append(iid)
        st, r = api("POST", f"/part-instances/{iid}/install", admin_token,
                    json={"device_id": device["id"], "device_code": device["device_code"], "deduct_stock": False})
        check("8-2 实例装机", st == 200, f"status={st} {r.get('status')}")
        st, r = api("POST", f"/part-instances/{iid}/return-in", admin_token, json={"warehouse_id": wh["id"]})
        check("8-3 实例拆回入库", st == 200, f"status={st} {r.get('status')}")
        st, r = api("POST", f"/part-instances/{iid}/rma", admin_token, json={"remark": "E2E 返厂"})
        check("8-4 实例返厂", st in (200, 400), f"status={st} {r.get('status') or r.get('detail')}")
        st, r = api("POST", f"/part-instances/{iid}/scrap", admin_token, json={"remark": "E2E 报废"})
        check("8-5 实例报废", st in (200, 400), f"status={st} {r.get('status') or r.get('detail')}")

    # ================= 9. 驾驶舱 / 统计 =================
    st, dash = api("GET", "/dashboard/stats", admin_token)
    check("9-1 驾驶舱统计", st == 200, f"status={st}")
    st, board = api("GET", "/work-orders/progress-board", admin_token)
    check("9-2 进度看板", st == 200, f"status={st}")
    st, dstat = api("GET", "/devices/monitor/stats", admin_token)
    check("9-3 设备监控统计", st == 200, f"status={st}")

    # ================= 11. 反向删除：约束行为 =================
    st, del_dev = api("DELETE", f"/devices/{device['id']}", admin_token)
    check("11-1 删除有工单的设备", st in (200, 400, 409),
          f"status={st} {del_dev.get('detail', '') if isinstance(del_dev, dict) else ''}")
    st, del_part = api("DELETE", f"/spare-parts/{part_a['id']}", admin_token)
    check("11-2 删除有流水的备件", st in (200, 400, 409),
          f"status={st} {del_part.get('detail', '') if isinstance(del_part, dict) else ''}")
    st, del_user = api("DELETE", f"/users/{tech_user['id']}", admin_token)
    check("11-3 删除有工单的技术员", st in (200, 400, 409),
          f"status={st} {del_user.get('detail', '') if isinstance(del_user, dict) else ''}")
    st, del_cust = api("DELETE", f"/customers/{cust['id']}", admin_token)
    check("11-4 删除有设备的客户", st in (200, 400, 409),
          f"status={st} {del_cust.get('detail', '') if isinstance(del_cust, dict) else ''}")
    st, del_wo = api("DELETE", f"/work-orders/{wo_id}", admin_token)
    if st in (200, 204):
        check("11-5 删除工单", True, f"status={st}")
        if wo_id in IDS["work_orders"]:
            IDS["work_orders"].remove(wo_id)
    else:
        gap("11-5 删除已消耗备件的工单报 500", f"status={st} "
            "（工单已产生 stock_movements / part_instances / requisitions 引用，"
            "delete_work_order 未先清关联行，库外键报错）")

    # ================= 10. 技术员权限矩阵（补充） =================
    matrix = [
        ("GET", "/users/", 200), ("POST", "/users/", 403),
        ("POST", "/customers/", None),
        ("DELETE", f"/customers/{cust['id']}", None),
        ("POST", "/devices/", None), ("DELETE", f"/devices/{device['id']}", None),
        ("POST", "/spare-parts/", 403), ("DELETE", f"/spare-parts/{part_b['id']}", 403),
        ("POST", "/warehouses/", 403), ("POST", "/stocktakes/", 403),
        ("POST", "/spare-parts/check-alerts", 403),
        ("GET", "/stocktakes/", 200), ("GET", "/spare-parts/alerts", 200),
        ("GET", "/customers/", None),
    ]
    for method, path, exp in matrix:
        st, body = api(method, path, tech_token, json={} if method in ("POST", "PUT") else None)
        if exp is not None:
            check(f"10 权限 {method} {path} 期望 {exp}", st == exp, f"实际={st}")
        else:
            verdict = {200: "允许", 201: "允许", 403: "拒绝", 400: "拒绝(参数)"}.get(st, f"其它 {st}")
            note = f"技术员 {method} {path} → {st}（{verdict}）"
            if method == "DELETE" and st == 200:
                gap("10-1 技术员可删除客户/设备", note + "；这类不可逆操作没有角色限制")
            elif method == "GET" and path == "/customers/" and st == 403:
                gap("10-2 技术员看不到客户列表", note + "；派工/建单要选客户时会缺数据")
            else:
                RESULTS.append({"name": note, "ok": True, "kind": "observe", "detail": note})
                print("[记录] " + note)
    # ================= 13. 其余模块：分类/故障码/知识/检索/请假/排班/巡检/保养/导出/系统设置 =================
    # 分类
    st, cat = api("POST", "/categories/", admin_token,
                  json={"name": f"E2E分类{RUN}", "code": f"E2E_CAT_{RUN}",
                        "category_type": "FAULT_PHENOMENON", "description": "E2E"})
    check("13-1 建分类", st in (200, 201), f"status={st}")
    cat_id = cat.get("id") if isinstance(cat, dict) else None
    if cat_id:
        st, _ = api("PUT", f"/categories/{cat_id}", admin_token,
                    json={"name": f"E2E分类改{RUN}", "code": f"E2E_CAT_{RUN}",
                          "category_type": "FAULT_PHENOMENON"})
        check("13-2 改分类", st == 200, f"status={st}")
        st, _ = api("DELETE", f"/categories/{cat_id}", admin_token)
        check("13-3 删分类", st in (200, 204), f"status={st}")
    st, deny_cat = api("POST", "/categories/", tech_token,
                json={"name": f"E2E越权分类{RUN}", "code": f"E2E_DENY_{RUN}",
                      "category_type": "FAULT_PHENOMENON"})
    if st in (200, 201):
        gap("13-4 技术员可建分类", f"status={st}；分类增删改没有角色限制（主管专属入口只在菜单层隐藏）")
        dc_id = deny_cat.get("id") if isinstance(deny_cat, dict) else None
        if dc_id:
            api("DELETE", f"/categories/{dc_id}", admin_token)
    else:
        check("13-4 技术员建分类被拒", st in (403, 401), f"status={st}")

    # 故障码
    st, fc = api("POST", "/fault-codes/create", admin_token,
                 json={"fault_description": f"E2E 故障码描述 {RUN}", "device_type": "GPU服务器"})
    check("13-5 建故障码映射", st in (200, 201), f"status={st} {fc.get('detail', '')}")
    fc_id = fc.get("id") if isinstance(fc, dict) else None
    if fc_id:
        st, _ = api("PUT", f"/fault-codes/{fc_id}", admin_token,
                    json={"fault_description": f"E2E 故障码描述改 {RUN}", "device_type": "GPU服务器"})
        check("13-6 改故障码", st == 200, f"status={st}")
        st, dt = api("GET", "/fault-codes/device-types", admin_token)
        check("13-7 故障码设备类型清单", st == 200, f"status={st}")
        st, _ = api("DELETE", f"/fault-codes/{fc_id}", admin_token)
        check("13-8 删故障码", st in (200, 204), f"status={st}")

    # 知识库：建 → 列表/检索 → 查重 → 删
    st, kn = api("POST", "/knowledge/", admin_token, json={
        "title": f"E2E 知识：GPU 掉卡处理 {RUN}",
        "content": "1. nvidia-smi -q 查 Xid；2. 换卡；3. 压测 2 小时。",
        "device_type": "GPU服务器", "fault_code": "XID79", "fault_tags": ["E2E", "GPU"]})
    check("13-9 建知识", st in (200, 201), f"status={st} {kn.get('detail', '')}")
    kn_id = kn.get("id") if isinstance(kn, dict) else None
    if kn_id:
        st, kl = api("GET", "/knowledge/", admin_token, params={"page_size": 5, "keyword": "E2E"})
        check("13-10 知识列表", st == 200, f"status={st}")
        st, ks = api("GET", "/knowledge/search", admin_token, params={"query": "GPU 掉卡"})
        check("13-11 知识检索", st == 200, f"status={st}")
        st, du = api("POST", f"/knowledge/{kn_id}/check-duplicate", admin_token, json={})
        check("13-12 知识查重", st in (200, 400, 422), f"status={st}")
        st, _ = api("PUT", f"/knowledge/{kn_id}", admin_token, json={
            "title": f"E2E 知识改：GPU 掉卡处理 {RUN}", "content": "更新内容"})
        check("13-13 知识只读(改被拒)", st == 403, f"status={st}（设计：知识库只读防污染）")
        st, _ = api("DELETE", f"/knowledge/{kn_id}", admin_token)
        check("13-14 知识只读(删被拒)", st == 403, f"status={st}")

    # 检索（无 Milvus 时降级 BM25）
    st, hy = api("POST", "/search/hybrid", admin_token,
                 json={"query": "GPU 掉卡 Xid 79", "top_k": 3})
    check("13-15 混合检索(降级BM25)", st == 200, f"status={st}")

    # 请假：技术员提交 → 管理员批准；管理员驳回
    st, lr = api("POST", "/leave-requests/", tech_token, json={
        "correlation_id": f"E2E-LEAVE-{RUN}",
        "leave_type": "PERSONAL", "leave_reason": f"E2E 事假 {RUN}",
        "date_from": "2026-12-01", "date_to": "2026-12-01", "shift_of_range": "ALL_DAY"})
    check("13-16 技术员提交请假", st in (200, 201), f"status={st} {lr.get('detail', '')}")
    lr_id = lr.get("id") if isinstance(lr, dict) else None
    if lr_id:
        st, lrm = api("GET", "/leave-requests/my", tech_token)
        check("13-17 我的请假列表", st == 200, f"status={st}")
        st, _ = api("POST", f"/leave-requests/{lr_id}/approve", tech_token, json={})
        check("13-18 技术员审批请假被拒", st == 403, f"status={st}")
        st, ap2 = api("POST", f"/leave-requests/{lr_id}/approve", admin_token,
                      json={"substitute_user_id": tech2["id"] if tech2 else None})
        check("13-19 管理员批准请假", st == 200, f"status={st} {ap2.get('detail', '')}")
        st, lr2 = api("POST", "/leave-requests/", tech_token, json={
            "correlation_id": f"E2E-LEAVE2-{RUN}", "leave_type": "PERSONAL",
            "leave_reason": "E2E 待驳回", "date_from": "2026-12-02", "date_to": "2026-12-02",
            "shift_of_range": "ALL_DAY"})
        lr2_id = lr2.get("id") if isinstance(lr2, dict) else None
        if lr2_id:
            st, rj = api("POST", f"/leave-requests/{lr2_id}/reject", admin_token,
                         json={"approver_comment": "E2E 当天缺人"})
            check("13-20 管理员驳回请假", st == 200, f"status={st} {rj.get('detail', '')}")
            api("POST", f"/leave-requests/{lr2_id}/cancel", tech_token)

    # 排班：今日 / 本周 / 班次元数据
    st, d1 = api("GET", "/duty-schedules/today", admin_token)
    check("13-21 今日排班", st == 200, f"status={st}")
    st, d2 = api("GET", "/duty-schedules/week", admin_token, params={"start_date": "2026-11-09"})
    check("13-22 本周排班", st == 200, f"status={st}")
    st, d3 = api("GET", "/duty-schedules/shift-meta", admin_token)
    check("13-23 班次元数据", st == 200, f"status={st}")

    # 点检：模板建/删 + 记录列表
    st, tpl = api("POST", "/inspections/templates", admin_token, json={
        "name": f"E2E 点检模板{RUN}", "device_type": "GPU服务器", "active": True,
        "items": [{"name": "GPU 温度", "standard": "<85℃", "method": "nvidia-smi"}]})
    check("13-24 建点检模板", st in (200, 201), f"status={st} {tpl.get('detail', '')}")
    tpl_id = tpl.get("id") if isinstance(tpl, dict) else None
    st, irec = api("GET", "/inspections/records", admin_token, params={"page_size": 5})
    check("13-25 点检记录列表", st == 200, f"status={st}")
    if tpl_id:
        st, _ = api("DELETE", f"/inspections/templates/{tpl_id}", admin_token)
        check("13-26 删点检模板", st in (200, 204), f"status={st}")

    # 保养：计划建 → 完成 → 删
    st, mp = api("POST", "/maintenance/plans", admin_token, json={
        "plan_name": f"E2E 保养计划{RUN}", "device_code": device["device_code"],
        "cycle_type": "MONTH", "cycle_value": 1, "remark": f"E2E {RUN}"})
    check("13-27 建保养计划", st in (200, 201), f"status={st} {mp.get('detail', '')}")
    mp_id = mp.get("id") if isinstance(mp, dict) else None
    if mp_id:
        st, st2 = api("GET", "/maintenance/stats", admin_token)
        check("13-28 保养统计", st == 200, f"status={st}")
        st, _ = api("POST", f"/maintenance/plans/{mp_id}/done", admin_token, json={})
        check("13-29 保养完成", st in (200, 400, 422), f"status={st}")
        st, mdel = api("DELETE", f"/maintenance/plans/{mp_id}", admin_token)
        if st in (200, 204):
            check("13-30 删保养计划", True, f"status={st}")
        else:
            fail_name = "13-30 删保养计划报 500"
            RESULTS.append({"name": fail_name, "ok": False, "kind": "fail",
                            "detail": f"status={st}（计划已产生保养记录，maintenance_records.plan_id 无级联）"})

    # 导出
    for path in ("/export/work-orders.xlsx", "/export/all.xlsx", "/export/spare-parts.xlsx"):
        try:
            r = S.get(API + path, headers={"Authorization": f"Bearer {admin_token}"}, timeout=60)
            ok = r.status_code == 200 and len(r.content) > 1000
        except Exception as e:
            r, ok = None, False
        check(f"13-31 导出 {path}", ok, f"status={getattr(r, 'status_code', 'ERR')} bytes={len(r.content) if r is not None else 0}")

    # 系统设置 / 通知 / 派工候选
    st, ov = api("GET", "/system-settings/overview", admin_token)
    check("13-32 系统设置概览(管理员)", st == 200, f"status={st}")
    st, _ = api("GET", "/system-settings/overview", tech_token)
    check("13-33 技术员看系统设置被拒", st == 403, f"status={st}")
    st, techs = api("GET", "/dispatch/technicians", admin_token)
    check("13-34 可派工技术员列表", st == 200 and len(techs if isinstance(techs, list) else techs.get("items", [])) >= 1,
          f"status={st}")
    st, _ = api("POST", "/notifications/read-all", tech_token)
    check("13-35 通知全部已读", st == 200, f"status={st}")
    st, mc = api("GET", "/manual-codes/", admin_token, params={"page_size": 5})
    check("13-36 手册错误码列表", st == 200, f"status={st}")
    st, q = api("GET", "/search/quick", admin_token, params={"q": "GPU", "limit": 5})
    check("13-37 快速搜索", st == 200, f"status={st}")


    # ================= 14. 清理 =================
    if not keep:
        cleanup(admin_token)
    else:
        print("--keep：保留测试数据，ID：", json.dumps(IDS, ensure_ascii=False))

    # ================= 15. 汇总 =================
    passed = sum(1 for r in RESULTS if r["kind"] == "pass")
    failed = [r for r in RESULTS if r["kind"] == "fail"]
    gaps = [r for r in RESULTS if r["kind"] == "gap"]
    print("\n=== 汇总：%d 通过 / %d 失败 / %d 项缺口 / 共 %d 项 ===" %
          (passed, len(failed), len(gaps), len(RESULTS)))
    for r in failed:
        print("  [FAIL]", r["name"], "|", r["detail"][:200])
    for r in gaps:
        print("  [GAP ]", r["name"], "|", r["detail"][:200])
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump({"run": RUN, "base": BASE, "results": RESULTS,
                   "summary": {"passed": passed, "failed": len(failed),
                               "gaps": len(gaps), "total": len(RESULTS)}},
                  f, ensure_ascii=False, indent=2)
    print("报告：", REPORT_PATH)
    return 0 if not failed else 1


def cleanup(admin_token):
    """按依赖倒序删除本脚本创建的数据；删除失败只记录不中断"""
    print("\n-- 清理测试数据 --")

    def rm(method, path, **kw):
        st, body = api(method, path, admin_token, **kw)
        return st, body

    for wid in list(IDS["work_orders"]):
        st, _ = rm("DELETE", f"/work-orders/{wid}")
        print(f"  工单 {wid} 删除 → {st}")
    for rid in IDS["requisitions"]:
        st, _ = api("POST", f"/spare-parts/requisitions/{rid}/cancel", admin_token)
        print(f"  领用单 {rid} 撤销 → {st}")
    for tid in IDS["stocktakes"]:
        st, _ = api("POST", f"/stocktakes/{tid}/cancel", admin_token)
        print(f"  盘点单 {tid} 作废 → {st}")
    for pid in IDS["parts"]:
        st, _ = rm("DELETE", f"/spare-parts/{pid}")
        print(f"  备件 {pid} 删除 → {st}")
    for did in IDS["devices"]:
        st, _ = rm("DELETE", f"/devices/{did}")
        print(f"  设备 {did} 删除 → {st}")
    for cid in IDS["customers"]:
        st, _ = rm("DELETE", f"/customers/{cid}")
        print(f"  客户 {cid} 删除 → {st}")
    for uid in IDS["users"]:
        st, _ = rm("DELETE", f"/users/{uid}")
        print(f"  用户 {uid} 删除 → {st}")
    for wid in IDS["warehouses"]:
        st, _ = rm("DELETE", f"/warehouses/{wid}")
        print(f"  仓库 {wid} 删除 → {st}")
    db_cleanup()


def db_cleanup(broad=False):
    """API 删不掉的残留（实例/流水/盘点明细）直接按测试编码清掉

    broad=True 时按 E2E 前缀清理所有历史残留（用于崩溃后重跑前的大扫除）。
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + r"\backend")
        from app.core.database import SessionLocal  # noqa
        from app.models.part_instance import PartInstance  # noqa
        from app.models.stock_movement import StockMovement  # noqa
        from app.models.spare_part import SparePart  # noqa
        from app.models.stocktake import Stocktake, StocktakeItem  # noqa
        from app.models.work_order import WorkOrder  # noqa
        from app.models.device import Device  # noqa
        from app.models.customer import Customer  # noqa
        from app.models.user import User  # noqa
        from app.models.warehouse import Warehouse, WarehouseLocation  # noqa
        from app.models.customer_site import CustomerSite  # noqa
        from app.models.customer_contact import CustomerContact  # noqa
    except Exception as e:
        print("  数据库兜底清理跳过：", e)
        return
    db = SessionLocal()
    try:
        from app.models.progress_log import WorkOrderProgressLog  # noqa
        from app.models.work_order_edit_log import WorkOrderEditLog  # noqa
        from app.models.work_order_collaborator import WorkOrderCollaborator  # noqa
        from app.models.notification import Notification  # noqa
        from app.models.spare_part_requisition import SparePartRequisition  # noqa
        from app.models.work_order_import import WorkOrderImportItem  # noqa
        from app.models.maintenance import MaintenancePlan, MaintenanceRecord  # noqa
        from app.models.login_log import LoginLog  # noqa
        from app.models.customer_device import CustomerDevice  # noqa

        # 1) 工单：先解引用再删（delete_work_order API 不做这一步，会 500）
        wos = db.query(WorkOrder).filter((WorkOrder.fault_description.like("%E2E%") if broad else WorkOrder.fault_description.like(f"%{RUN}%"))).all()
        wo_ids = [w.id for w in wos]
        if wo_ids:
            db.query(StockMovement).filter(StockMovement.work_order_id.in_(wo_ids)).update(
                {"work_order_id": None}, synchronize_session=False)
            db.query(PartInstance).filter(PartInstance.work_order_id.in_(wo_ids)).update(
                {"work_order_id": None}, synchronize_session=False)
            for model in (SparePartRequisition, MaintenancePlan, MaintenanceRecord, WorkOrderImportItem):
                try:
                    db.query(model).filter(model.work_order_id.in_(wo_ids)).update(
                        {"work_order_id": None}, synchronize_session=False)
                except Exception:
                    pass
            db.query(Notification).filter(Notification.work_order_id.in_(wo_ids)).delete(synchronize_session=False)
            db.query(WorkOrderProgressLog).filter(WorkOrderProgressLog.work_order_id.in_(wo_ids)).delete(
                synchronize_session=False)
            db.query(WorkOrderEditLog).filter(WorkOrderEditLog.work_order_id.in_(wo_ids)).delete(
                synchronize_session=False)
            db.query(WorkOrderCollaborator).filter(WorkOrderCollaborator.work_order_id.in_(wo_ids)).delete(
                synchronize_session=False)
            for wid in wo_ids:
                db.query(WorkOrder).filter(WorkOrder.id == wid).delete(synchronize_session=False)
        # 2) 盘点单先删（它的明细 movement_id 指向库存流水，删流水前必须先清）
        takes = db.query(Stocktake).filter((Stocktake.remark.like("E2E%") if broad else Stocktake.remark.like(f"%{RUN}%"))).all()
        for t in takes:
            db.query(StocktakeItem).filter(StocktakeItem.stocktake_id == t.id).delete(synchronize_session=False)
            db.delete(t)

        # 2) 备件：实例/流水/领用单先删
        parts = db.query(SparePart).filter((SparePart.part_code.like("E2E%") if broad else SparePart.part_code.like(f"%{RUN}%"))).all()
        pids = [p.id for p in parts]
        if pids:
            # 领用单的 movement_id 指向流水，必须先删领用单再删流水
            db.query(SparePartRequisition).filter(SparePartRequisition.part_id.in_(pids)).delete(
                synchronize_session=False)
            db.query(PartInstance).filter(PartInstance.part_id.in_(pids)).delete(synchronize_session=False)
            db.query(StockMovement).filter(StockMovement.part_id.in_(pids)).delete(synchronize_session=False)
        for p in parts:
            db.delete(p)
        # 2b) 其余模块：点检记录 / 保养记录 / 分类 / 知识 / 请假 / 计划 / 模板
        from app.models.category import Category
        from app.models.knowledge import KnowledgeItem
        from app.models.leave_request import LeaveRequest
        from app.models.maintenance import InspectionTemplate, InspectionRecord
        steps = [
            lambda: db.query(InspectionRecord).filter(InspectionRecord.template_name.like("E2E%")).delete(synchronize_session=False),
            lambda: db.query(MaintenanceRecord).filter(MaintenanceRecord.plan_id.in_(
                db.query(MaintenancePlan.id).filter(MaintenancePlan.plan_name.like("E2E%")))).delete(synchronize_session=False),
            lambda: db.query(MaintenancePlan).filter(MaintenancePlan.plan_name.like("E2E%")).delete(synchronize_session=False),
            lambda: db.query(InspectionTemplate).filter(InspectionTemplate.name.like("E2E%")).delete(synchronize_session=False),
            lambda: db.query(Category).filter(Category.code.like("E2E_%")).delete(synchronize_session=False),
            lambda: db.query(KnowledgeItem).filter(KnowledgeItem.title.like("E2E%")).delete(synchronize_session=False),
            lambda: db.query(LeaveRequest).filter(LeaveRequest.correlation_id.like("E2E-%")).delete(synchronize_session=False),
        ]
        for fn in steps:
            try:
                with db.begin_nested():
                    fn()
            except Exception as e:
                print("  清理步骤跳过：", type(e).__name__, str(e)[:120])

        # 3) 设备 / 客户 / 用户 / 仓库
        devs = db.query(Device).filter(
            (Device.device_code.like("E2E%") if broad else Device.device_code.like(f"%{RUN}%"))).all()
        dev_ids = [d.id for d in devs]
        if dev_ids:
            db.query(CustomerDevice).filter(CustomerDevice.device_id.in_(dev_ids)).delete(synchronize_session=False)
            for model in (MaintenancePlan, MaintenanceRecord):
                try:
                    db.query(model).filter(model.device_id.in_(dev_ids)).delete(synchronize_session=False)
                except Exception:
                    pass
            db.query(PartInstance).filter(PartInstance.device_id.in_(dev_ids)).update(
                {"device_id": None}, synchronize_session=False)
        for d in devs:
            db.delete(d)
        for c in db.query(Customer).filter(
                (Customer.name.like("E2E%") if broad else Customer.name.like(f"%{RUN}%"))).all():
            db.query(CustomerSite).filter(CustomerSite.customer_id == c.id).delete(synchronize_session=False)
            db.query(CustomerContact).filter(CustomerContact.customer_id == c.id).delete(synchronize_session=False)
            db.delete(c)
        users = db.query(User).filter(
            (User.username.like("e2e_%") if broad else User.username.like(f"%e2e_%{RUN}%"))).all()
        uids = [u.id for u in users]
        if uids:
            from sqlalchemy import or_
            db.query(LoginLog).filter(LoginLog.user_id.in_(uids)).delete(synchronize_session=False)
            db.query(Notification).filter(Notification.user_id.in_(uids)).delete(synchronize_session=False)
            db.query(SparePartRequisition).filter(
                or_(SparePartRequisition.applicant_id.in_(uids),
                    SparePartRequisition.approver_id.in_(uids))).delete(synchronize_session=False)
            db.query(StockMovement).filter(StockMovement.operator_id.in_(uids)).update(
                {"operator_id": None}, synchronize_session=False)
            db.query(Customer).filter(Customer.owner_id.in_(uids)).update(
                {"owner_id": None}, synchronize_session=False)
            db.query(Stocktake).filter(Stocktake.created_by.in_(uids)).update(
                {"created_by": None}, synchronize_session=False)
            db.query(Stocktake).filter(Stocktake.approved_by.in_(uids)).update(
                {"approved_by": None}, synchronize_session=False)
        for u in users:
            db.delete(u)

        for w in db.query(Warehouse).filter((Warehouse.code.like("E2E-%") if broad else Warehouse.code.like(f"%{RUN}%"))).all():
            db.query(WarehouseLocation).filter(WarehouseLocation.warehouse_id == w.id).delete(
                synchronize_session=False)
            db.delete(w)
        db.commit()
        print("  数据库兜底清理完成")
    except Exception as e:
        db.rollback()
        print("  数据库兜底清理失败：", type(e).__name__, e)
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="保留测试数据")
    args = ap.parse_args()
    sys.exit(main(keep=args.keep))

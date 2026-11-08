# -*- coding: utf-8 -*-
"""审计第五轮：角色权限矩阵 + 状态机边界"""
import io
import json
import sys

import psycopg2
import requests

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:18080"
API = BASE + "/api/v1"
OUT = r"C:\Users\aaa\AppData\Local\Temp\xgsz-audit-perm.txt"
lines = []


def w(x=""):
    lines.append(str(x))
    print(str(x))


def login(u, p):
    r = requests.post(API + "/auth/login-by-password", json={"username": u, "password": p}, timeout=20)
    return r.json().get("token") if r.status_code == 200 else None


admin = requests.Session()
admin.headers["Authorization"] = f"Bearer {login('admin', 'admin123')}"
tech = requests.Session()
t = login("zhangwei", "newpass123")
tech.headers["Authorization"] = f"Bearer {t}" if t else ""
w(f"admin token={'有' if admin.headers['Authorization']!='Bearer ' else '无'}  "
  f"technician token={'有' if t else '无'}")

conn = psycopg2.connect(host="localhost", port=15432, user="admin", dbname="xgsz_maintain")
conn.autocommit = True
cur = conn.cursor()
cur.execute("select id, work_order_no, status, coalesce(created_by,-1), coalesce(technician_id,-1) from work_orders order by id")
rows = cur.fetchall()
w("\n## 工单现状")
for r in rows:
    w(f"  id={r[0]} {r[1]:20} {r[2]:10} created_by={r[3]} technician={r[4]}")
null_created = [r for r in rows if r[3] == -1]
w(f"  created_by 为空的工单：{[r[0] for r in null_created]}（删除权限校验会被跳过）")

w("\n## 维修员（TECHNICIAN）调高权限接口")
checks = [
    ("GET", "/users/", None),
    ("POST", "/users/", {"username": "atk_admin", "real_name": "越权测试", "role": "ADMIN", "password": "x123456"}),
    ("GET", "/users/1", None),
    ("POST", "/spare-parts/", {"part_code": "AUDIT-1", "part_name": "审计", "stock_quantity": 1}),
    ("DELETE", "/spare-parts/1", None),
    ("GET", "/leave-requests/", None),
    ("POST", "/leave-requests/approve", {"request_id": 1}),
    ("GET", "/categories/data/fault-phenomena", None),
]
for m, p, body in checks:
    try:
        if body is None:
            r = tech.request(m, API + p, timeout=20)
        else:
            r = tech.request(m, API + p, json=body, timeout=20)
        w(f"  {m:6} {p:42} -> {r.status_code} {str(r.text)[:70] if r.status_code >= 400 else ''}")
    except Exception as e:
        w(f"  {m:6} {p:42} -> EXC {e}")

w("\n## created_by=NULL 的工单，维修员能否删除（越权点）")
if null_created:
    victim = null_created[0][0]
    r = tech.delete(API + f"/work-orders/{victim}", timeout=20)
    w(f"  DELETE /work-orders/{victim}（维修员）-> {r.status_code} {str(r.text)[:80]}")
    if r.status_code == 200:
        w("  ★ 说明：无创建者工单可被任意登录用户删除")

w("\n## 状态机边界（管理员）")
r = admin.post(API + "/work-orders/", json={"fault_description": "审计用-状态机", "device_code": "CNC-L-001"}, timeout=20)
wo = r.json()["id"]
w(f"  新建 id={wo} 状态={r.json()['status']}")

def trans(wid, to, note=""):
    rr = admin.post(API + f"/work-orders/{wid}/transition", json={"to_status": to, "remark": note}, timeout=20)
    return rr.status_code, (rr.json().get("status") or rr.json().get("detail"))

for to in ("ARCHIVED", "COMPLETED"):
    code, detail = trans(wo, to)
    w(f"  transition -> {to:10} => {code} {str(detail)[:70]}")
code, detail = trans(wo, "ASSIGNED", "跳过 SUBMITTED 直接派工")
w(f"  DRAFT 直接 -> ASSIGNED => {code} {detail}")
code, detail = trans(wo, "ASSIGNED")
w(f"  重复 -> ASSIGNED（幂等？）=> {code} {detail}")

cur.execute("delete from work_orders where id=%s", (wo,))
w(f"  清理测试工单 id={wo}：{cur.rowcount} 行")

w("\n## 归档接口的边界")
r = admin.post(API + "/work-orders/2/archive-check", timeout=20)
w(f"  DRAFT 工单调用 archive-check -> {r.status_code} {str(r.text)[:80]}")
r = admin.post(API + "/work-orders/99999/archive-complete", timeout=20)
w(f"  不存在工单 archive-complete -> {r.status_code}")

conn.close()
open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n->", OUT)

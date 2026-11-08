# -*- coding: utf-8 -*-
"""审计第六轮：导入边界用例 + 性能 + 数据泄露字段"""
import io
import os
import sys
import tempfile
import time

import requests
from openpyxl import Workbook

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:18080"
API = BASE + "/api/v1"
OUT = r"C:\Users\aaa\AppData\Local\Temp\xgsz-audit-import.txt"
lines = []


def w(x=""):
    lines.append(str(x))
    print(str(x))


def login(u, p):
    r = requests.post(API + "/auth/login-by-password", json={"username": u, "password": p}, timeout=20)
    return r.json().get("token") if r.status_code == 200 else None


s = requests.Session()
s.headers["Authorization"] = f"Bearer {login('admin', 'admin123')}"
tech = requests.Session()
tech.headers["Authorization"] = f"Bearer {login('zhangwei', 'newpass123')}"
tmp = tempfile.mkdtemp(prefix="audit-")


def post_excel(path, name=None):
    name = name or os.path.basename(path)
    with open(path, "rb") as f:
        return s.post(API + "/work-order-imports/upload-excel",
                      files={"file": (name, f, "application/octet-stream")}, timeout=300)


w("## 1. 维修员能看到用户列表，字段是否含隐私")
r = tech.get(API + "/users/", params={"page": 1, "page_size": 2}, timeout=20)
if r.status_code == 200:
    j = r.json()
    items = j.get("items", j if isinstance(j, list) else [])
    keys = sorted(items[0].keys()) if items else []
    w(f"  GET /users/ -> 200，返回字段：{keys}")
    sample = items[0] if items else {}
    w(f"  样例：username={sample.get('username')} phone={sample.get('phone')} "
      f"email={sample.get('email')} employee_id={sample.get('employee_id')}")

w("\n## 2. Excel 边界用例")
# 2.1 只有表头
p = os.path.join(tmp, "only-header.xlsx")
wb = Workbook(); ws = wb.active
ws.append(["工单号", "设备编号", "故障描述"])
wb.save(p)
t0 = time.time(); r = post_excel(p); dt = time.time() - t0
w(f"  只有表头 -> {r.status_code} {str(r.text)[:110]} ({dt:.2f}s)")

# 2.2 空文件（0 字节）
p = os.path.join(tmp, "empty.xlsx"); open(p, "wb").close()
r = post_excel(p)
w(f"  0 字节 xlsx -> {r.status_code} {str(r.text)[:110]}")

# 2.3 伪装的 .xlsx（其实是文本）
p = os.path.join(tmp, "fake.xlsx")
open(p, "w", encoding="utf-8").write("这不是 excel")
r = post_excel(p)
w(f"  伪装 xlsx（纯文本）-> {r.status_code} {str(r.text)[:110]}")

# 2.4 同文件内重复工单号
p = os.path.join(tmp, "dup.xlsx")
wb = Workbook(); ws = wb.active
ws.append(["工单号", "设备编号", "故障描述"])
for _ in range(2):
    ws.append(["WO-DUP-001", "CNC-L-001", "重复工单号测试"])
wb.save(p)
r = post_excel(p)
j = r.json() if r.status_code == 200 else {}
w(f"  同文件重复工单号 -> {r.status_code} pending={j.get('pending')} failed={j.get('failed')} "
  f"结果={j.get('results')}")

# 2.5 脏数据：非法日期 + 超长文本 + 负数工时
p = os.path.join(tmp, "dirty.xlsx")
wb = Workbook(); ws = wb.active
ws.append(["工单号", "设备编号", "故障描述", "维修工时", "报修时间"])
ws.append(["WO-DIRTY-001", "CNC-L-001", "A" * 5000, -3, "不是日期"])
wb.save(p)
r = post_excel(p)
j = r.json() if r.status_code == 200 else {}
w(f"  脏数据（超长文本/负工时/非法日期）-> {r.status_code} "
  f"pending={j.get('pending')} failed={j.get('failed')} 提示={j.get('results')}")

# 2.6 UTF-8 BOM 的 CSV
p = os.path.join(tmp, "bom.csv")
open(p, "w", encoding="utf-8-sig", newline="").write("工单号,设备编号,故障描述\nWO-BOM-001,AC-003,BOM 测试\n")
r = post_excel(p)
j = r.json() if r.status_code == 200 else {}
w(f"  UTF-8 BOM CSV -> {r.status_code} pending={j.get('pending')} failed={j.get('failed')}")

# 2.7 500 行性能
p = os.path.join(tmp, "big.xlsx")
wb = Workbook(); ws = wb.active
ws.append(["工单号", "设备编号", "故障描述", "维修人", "维修工时"])
for i in range(500):
    ws.append([f"WO-PERF-{i:04d}", "CNC-L-001", f"性能测试故障描述 {i}", "张伟", 1.5])
wb.save(p)
t0 = time.time(); r = post_excel(p); dt = time.time() - t0
j = r.json() if r.status_code == 200 else {}
w(f"  500 行导入 -> {r.status_code} pending={j.get('pending')} failed={j.get('failed')} 耗时 {dt:.2f}s")

w("\n## 3. 性能抽查")
for name, fn in [
    ("工单列表 page_size=100", lambda: s.get(API + "/work-orders/", params={"page": 1, "page_size": 100}, timeout=60)),
    ("工单列表 keyword 模糊查", lambda: s.get(API + "/work-orders/", params={"keyword": "主轴", "page_size": 20}, timeout=60)),
    ("待确认清单（含 500 条）", lambda: s.get(API + "/work-order-imports/items", params={"status": "PENDING", "page": 1, "page_size": 50}, timeout=60)),
    ("混合检索", lambda: s.post(API + "/search/hybrid", json={"query": "主轴异响", "top_k": 10, "mode": "hybrid"}, timeout=60)),
    ("驾驶舱", lambda: s.get(API + "/dashboard/stats", timeout=60)),
]:
    t0 = time.time()
    try:
        r = fn()
        w(f"  {name:26} -> {r.status_code}  {time.time()-t0:.2f}s")
    except Exception as e:
        w(f"  {name:26} -> EXC {type(e).__name__}")

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n->", OUT)

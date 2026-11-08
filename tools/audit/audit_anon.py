# -*- coding: utf-8 -*-
"""审计第二轮：匿名访问实证（带清理）"""
import base64
import json
import os

import psycopg2
import requests

BASE = "http://127.0.0.1:18080"
API = BASE + "/api/v1"
OUT = r"C:\Users\aaa\AppData\Local\Temp\xgsz-audit-anon.txt"
lines = []


def w(s=""):
    lines.append(str(s))
    print(str(s))


s = requests.Session()  # 不带任何 token

w("## 1. 匿名读工单详情")
r = s.get(API + "/work-orders/1", timeout=20)
w(f"  GET /work-orders/1 -> {r.status_code}")
if r.status_code == 200:
    d = r.json()
    w(f"  暴露字段：工单号={d.get('work_order_no')} 故障描述={str(d.get('fault_description'))[:30]!r} "
      f"状态={d.get('status')} 附件数={len(d.get('attachments') or [])}")

w("\n## 2. 匿名读知识库")
for path in ("/knowledge/1", "/knowledge/", "/knowledge/solutions?fault_code=SMOKE-001"):
    rr = s.get(API + path, timeout=20)
    w(f"  GET {path} -> {rr.status_code}")

w("\n## 3. 匿名创建知识条目（写操作）")
payload = {"title": "AUDIT-TEST-请忽略", "content": "这是一条审计脚本写入的测试知识，稍后会被删除。",
           "device_type": "CNC", "status": "PUBLISHED"}
r = s.post(API + "/knowledge/", json=payload, timeout=20)
w(f"  POST /knowledge/ -> {r.status_code} {str(r.text)[:120]}")
new_id = None
if r.status_code in (200, 201):
    new_id = r.json().get("id")
    w(f"  ★ 成功写入知识 id={new_id}（匿名可写知识库）")

w("\n## 4. 匿名上传文件")
png = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
r = s.post(API + "/upload/work-order-image",
           files={"file": ("audit-test.png", png, "image/png")}, timeout=60)
w(f"  POST /upload/work-order-image -> {r.status_code} {str(r.text)[:160]}")
uploaded = r.json().get("url") if r.status_code == 200 else None

w("\n## 5. 匿名触发验证码发送")
r = s.post(API + "/auth/send-code", json={"phone": "13800000000"}, timeout=20)
w(f"  POST /auth/send-code -> {r.status_code} {str(r.text)[:200]}")

w("\n## 6. 匿名读取设备/分类字典（信息收集面）")
for path in ("/devices?page=1&page_size=3", "/devices/monitor/stats",
             "/categories/data/fault-phenomena", "/categories/data/root-causes"):
    rr = s.get(API + path, timeout=20)
    body = ""
    if rr.status_code == 200:
        try:
            j = rr.json()
            if isinstance(j, dict) and "items" in j:
                body = f"items={len(j['items'])} total={j.get('total')}"
            elif isinstance(j, list):
                body = f"len={len(j)}"
            else:
                body = str(j)[:60]
        except Exception:
            body = rr.text[:60]
    w(f"  GET {path} -> {rr.status_code} {body}")

# ---- 清理
w("\n## 清理")
conn = psycopg2.connect(host="localhost", port=15432, user="admin", dbname="xgsz_maintain")
conn.autocommit = True
cur = conn.cursor()
if new_id:
    cur.execute("DELETE FROM knowledge_items WHERE id = %s", (new_id,))
    w(f"  已删除测试知识 id={new_id}（影响 {cur.rowcount} 行）")
if uploaded:
    p = os.path.join(r"C:\Users\aaa\Desktop\xgsz-maintain\backend\uploads",
                     os.path.basename(uploaded))
    if os.path.exists(p):
        os.remove(p)
        w(f"  已删除测试上传文件 {os.path.basename(p)}")
cur.execute("SELECT count(*) FROM knowledge_items")
w(f"  knowledge_items 现有 {cur.fetchone()[0]} 条")
conn.close()

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n->", OUT)

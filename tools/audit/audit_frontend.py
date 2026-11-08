# -*- coding: utf-8 -*-
"""审计第七轮：前端运行时——控制台报错 / 失败请求 / 首屏耗时"""
import io
import os
import sys
import time

import requests
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:18080"
API = BASE + "/api/v1"
OUT = r"C:\Users\aaa\AppData\Local\Temp\xgsz-audit-frontend.txt"
lines = []


def w(x=""):
    lines.append(str(x))
    print(str(x))


r = requests.post(API + "/auth/login-by-password", json={"username": "admin", "password": "admin123"}, timeout=20).json()
token, user = r["token"], r

PAGES = [("登录", "/login"), ("驾驶舱", "/dashboard"), ("维修报表", "/work-orders"),
         ("工单详情", "/work-orders/1"), ("新建工单", "/work-orders/new"),
         ("历史工单导入", "/work-order-imports"), ("AI 问答", "/ai-assistant"),
         ("知识库", "/knowledge/list"), ("设备监控", "/devices"), ("备件台账", "/spare-parts"),
         ("用户管理", "/users"), ("派工中心", "/supervisor/dispatch"), ("通知中心", "/notifications")]

with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    page = ctx.new_page()
    errors, failed = [], []
    page.on("console", lambda m: errors.append(f"[{m.type}] {m.text[:200]}") if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: errors.append(f"[pageerror] {str(e)[:200]}"))
    page.on("requestfailed", lambda req: failed.append(f"{req.method} {req.url[:110]} :: {req.failure}"))
    page.on("response", lambda resp: failed.append(f"{resp.status} {resp.request.method} {resp.url[:110]}")
            if resp.status >= 400 else None)

    page.goto(BASE + "/login", wait_until="networkidle")
    page.evaluate("([t,u]) => { localStorage.setItem('auth_token', t); localStorage.setItem('current_user', JSON.stringify(u)); }",
                  [token, user])
    time.sleep(0.5)

    for name, path in PAGES:
        errors.clear(); failed.clear()
        t0 = time.time()
        try:
            page.goto(BASE + path, wait_until="networkidle", timeout=45000)
            time.sleep(1.4)
            dt = time.time() - t0
            title = page.title()
            body = page.inner_text("body")[:60].replace("\n", " ")
            w(f"\n### {name} {path}  加载 {dt:.2f}s")
            w(f"  标题={title[:30]}  正文开头={body!r}")
            if errors:
                w(f"  ⚠ 控制台 {len(errors)} 条：")
                for e in errors[:6]:
                    w(f"    - {e}")
            if failed:
                w(f"  ⚠ 失败请求 {len(failed)} 条：")
                for f in failed[:8]:
                    w(f"    - {f}")
            if not errors and not failed:
                w("  ✓ 无报错/失败请求")
        except Exception as e:
            w(f"\n### {name} {path}  ★ 打开失败：{type(e).__name__} {str(e)[:120]}")

    browser.close()

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n->", OUT)

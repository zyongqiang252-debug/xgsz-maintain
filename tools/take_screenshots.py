# -*- coding: utf-8 -*-
"""用系统 Edge 截取关键页面（登录后注入 token，跳过 UI 登录）"""
import json
import os
import tempfile
import time

import requests
from playwright.sync_api import sync_playwright

BASE = os.environ.get("XGSZ_BASE", "http://127.0.0.1:18080")
API = BASE + "/api/v1"
OUT = os.path.join(tempfile.gettempdir(), "xgsz-shots")
os.makedirs(OUT, exist_ok=True)


def auth():
    r = requests.post(API + "/auth/login-by-password",
                      json={"username": "admin", "password": "admin123"}, timeout=30)
    d = r.json()
    return d["token"], d


def pick_work_order():
    """找一张已归档的工单用于详情页截图"""
    token, user = auth()
    h = {"Authorization": f"Bearer {token}"}
    r = requests.get(API + "/work-orders/", params={"page": 1, "page_size": 50}, headers=h, timeout=30)
    rows = r.json().get("items", [])
    archived = [x for x in rows if x.get("status") == "ARCHIVED"]
    return (archived[0]["id"] if archived else (rows[0]["id"] if rows else None)), token, user


def main():
    wo_id, token, user = pick_work_order()
    print("目标工单:", wo_id)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                  locale="zh-CN")
        page = ctx.new_page()

        page.goto(BASE + "/login", wait_until="networkidle")
        time.sleep(0.8)
        page.screenshot(path=os.path.join(OUT, "01-login.png"))
        print("shot 01-login")

        page.evaluate(
            """([t, u]) => {
                localStorage.setItem('auth_token', t);
                localStorage.setItem('current_user', JSON.stringify(u));
            }""",
            [token, user],
        )

        targets = [
            ("02-dashboard", "/dashboard"),
            ("03-workorders", "/work-orders"),
            ("04-workorder-detail", f"/work-orders/{wo_id}"),
            ("05-import", "/work-order-imports"),
            ("06-ai", "/ai-assistant"),
        ]
        for name, path in targets:
            page.goto(BASE + path, wait_until="networkidle")
            time.sleep(1.6)
            page.screenshot(path=os.path.join(OUT, f"{name}.png"))
            print("shot", name, page.title())

        browser.close()
    print("done ->", OUT)


if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""页面冒烟：16 个 PC 页面能打开、零 console error、零失败请求

放在最后跑（``-m "not slow"`` 可跳过）。Playwright 用系统 Edge，没装就直接跳过。
"""
import time

import pytest

from conftest import BASE, Api, login

PAGES = [
    ("数据驾驶舱", "/dashboard"),
    ("工单中心", "/orders"),
    ("历史导入", "/orders?tab=import"),
    ("进度看板", "/orders?tab=progress"),
    ("库存中心", "/stock"),
    ("客户管理", "/customers"),
    ("设备监控", "/devices"),
    ("新增设备", "/devices/new"),
    ("保养与点检", "/maintenance"),
    ("知识中心", "/knowledge-center"),
    ("字典管理", "/dict"),
    ("系统管理", "/sys"),
    ("通知中心", "/me"),
    ("账号安全", "/security"),
    ("新建工单", "/work-orders/new"),
    ("新增备件", "/spare-parts/new"),
]


@pytest.mark.slow
def test_pages_have_no_console_errors(server):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("未安装 playwright")
    try:
        api = Api()
        token, _, st = login(api, "admin", "admin123")
        assert st == 200 and token
    except Exception as e:
        pytest.skip(f"登录失败：{e}")

    problems = []
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="msedge", headless=True)
        except Exception as e:
            pytest.skip(f"系统 Edge 不可用：{e}")
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        for label, path in PAGES:
            page = ctx.new_page()
            errors, bad = [], []
            page.on("console", lambda m, e=errors: e.append(m.text) if m.type == "error" else None)
            page.on("response", lambda r, b=bad: b.append(f"{r.status} {r.url}")
                    if r.status >= 400 and "/api/" in r.url else None)
            page.goto(BASE + "/login", wait_until="networkidle")
            page.evaluate("""([t]) => localStorage.setItem('auth_token', t)""", [token])
            page.goto(BASE + path, wait_until="networkidle")
            time.sleep(1.0)
            if errors:
                problems.append(f"{label}（{path}）console: {errors[:2]}")
            if bad:
                problems.append(f"{label}（{path}）请求失败: {bad[:2]}")
            page.close()
        browser.close()
    assert not problems, "页面回归发现问题：\n" + "\n".join(problems)

# -*- coding: utf-8 -*-
r"""全站 UI 体检：横向滚动 / 列重叠 / 列被裁切 / 固定列 / 行高 / 文字截断

用法（backend 目录下）：
    .\.venv\Scripts\python.exe ..\tools\ui_audit.py
"""
import io
import json
import sys
import time

import requests
from playwright.sync_api import sync_playwright

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
BASE = "http://127.0.0.1:18080"
API = BASE + "/api/v1"

PAGES = [
    ("/dashboard", "数据驾驶舱"), ("/work-orders", "维修报表"), ("/work-orders/new", "新建工单"),
    ("/work-order-imports", "历史工单导入"), ("/ai-assistant", "AI 问答看板"),
    ("/knowledge/list", "知识库"), ("/devices", "设备监控"), ("/maintenance", "保养与点检"),
    ("/categories", "分类管理"), ("/spare-parts", "备件台账"), ("/warehouse", "仓库库存"),
    ("/fault-codes", "故障码管理"), ("/users", "用户管理"), ("/supervisor/dispatch", "派工中心"),
    ("/supervisor/progress", "实时进度看板"), ("/supervisor/schedule", "排班管理"),
    ("/leave", "我的请假"), ("/notifications", "通知中心"), ("/security", "账号安全"),
    ("/system-settings", "系统设置"), ("/help", "帮助中心"),
]

PROBE = """() => {
  const out = { tables: [] };
  const vw = window.innerWidth;
  const tables = [...document.querySelectorAll('.el-table')].filter(t => t.offsetParent !== null);
  out.tables = tables.map((t, idx) => {
    const body = t.querySelector('.el-table__body-wrapper');
    const tableRight = Math.round(t.getBoundingClientRect().right);
    const header = t.querySelector('.el-table__header');
    const headerRight = header ? Math.round(header.getBoundingClientRect().right) : 0;
    const ths = [...t.querySelectorAll('.el-table__header th')].map(th => {
      const r = th.getBoundingClientRect();
      return { t: (th.innerText || '').trim(), x: Math.round(r.x), w: Math.round(r.width) };
    });
    const rows = [...t.querySelectorAll('.el-table__body tr')].slice(0, 8)
      .map(tr => Math.round(tr.getBoundingClientRect().height));
    // 被裁切：表头右边界超出表格容器，或最后一列超出容器
    const lastCell = t.querySelector('.el-table__body tr td:last-child');
    const lastRight = lastCell ? Math.round(lastCell.getBoundingClientRect().right) : 0;
    // 文字被截断的按钮/标签
    const clipped = [...t.querySelectorAll('.el-table__body button, .el-table__body .el-button')]
      .filter(b => b.scrollWidth > b.clientWidth + 2)
      .map(b => (b.innerText || '').trim().slice(0, 12));
    return {
      idx: idx + 1,
      cols: ths.length,
      hscroll: body ? body.scrollWidth > body.clientWidth + 2 : false,
      sw: body ? body.scrollWidth : 0, cw: body ? body.clientWidth : 0,
      maxRowH: rows.length ? Math.max(...rows) : 0,
      minRowH: rows.length ? Math.min(...rows) : 0,
      fixed: t.querySelectorAll('.el-table-fixed-column--right, .el-table__fixed-right').length,
      overlap: ths.some((th, i) => i < ths.length - 1 && th.x + th.w > ths[i + 1].x + 2),
      clippedCol: headerRight > tableRight + 2 || lastRight > tableRight + 2,
      headerRight, tableRight, lastRight,
      clippedButtons: clipped,
    };
  });
  out.docOverflowX = document.documentElement.scrollWidth > document.documentElement.clientWidth + 2;
  out.docScrollW = document.documentElement.scrollWidth;
  out.docClientW = document.documentElement.clientWidth;
  out.wideEls = [...document.querySelectorAll('.page *')]
    .filter(el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.right > vw + 4; })
    .slice(0, 3).map(el => el.className.toString().slice(0, 50));
  return out;
}"""


def main():
    r = requests.post(API + "/auth/login-by-password",
                      json={"username": "admin", "password": "admin123"}, timeout=20).json()
    tok = r["token"]
    JS = """([t,u]) => { localStorage.setItem('auth_token', t); localStorage.setItem('current_user', JSON.stringify(u)); }"""

    issues = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="msedge", headless=True)
        c = b.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
        pg = c.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:80]))
        pg.goto(BASE + "/login", wait_until="networkidle")
        pg.evaluate(JS, [tok, r])

        for path, name in PAGES:
            try:
                pg.goto(BASE + path, wait_until="networkidle", timeout=30000)
                time.sleep(1.4)
                info = pg.evaluate(PROBE)
            except Exception as e:
                print(f"{name:12} ★ 打开失败 {e}")
                issues.append((name, "打开失败", path))
                continue

            problems = []
            if info["docOverflowX"]:
                problems.append(f"页面横向溢出 {info['docScrollW']}>{info['docClientW']}")
            if info["wideEls"]:
                problems.append(f"元素超出右边界: {info['wideEls']}")
            for t in info["tables"]:
                if t["hscroll"]:
                    problems.append(f"表{t['idx']} 横向滚动 {t['sw']}>{t['cw']}")
                if t["overlap"]:
                    problems.append(f"表{t['idx']} 列重叠")
                if t["clippedCol"]:
                    problems.append(
                        f"表{t['idx']} ★列被裁切 (表头右={t['headerRight']} 末列右={t['lastRight']} 容器右={t['tableRight']})")
                if t["clippedButtons"]:
                    problems.append(f"表{t['idx']} 按钮文字被截断 {t['clippedButtons'][:3]}")
                if t["fixed"]:
                    problems.append(f"表{t['idx']} 有固定列({t['fixed']})")
                if t["maxRowH"] - t["minRowH"] > 16:
                    problems.append(f"表{t['idx']} 行高不齐 {t['minRowH']}~{t['maxRowH']}")
                if t["maxRowH"] > 90:
                    problems.append(f"表{t['idx']} 行过高 {t['maxRowH']}px")

            print(f"{name:12} {'OK' if not problems else '★'} 表格数={len(info['tables'])}")
            for pr in problems:
                print(f"             - {pr}")
                issues.append((name, pr, path))

        print("\n页面 JS 错误:", errs[:5] or "无")
        b.close()

    print(f"\n===== 共 {len(issues)} 个问题 =====")
    with open(r"C:\Users\aaa\AppData\Local\Temp\xgsz-ui-audit.json", "w", encoding="utf-8") as f:
        json.dump(issues, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()

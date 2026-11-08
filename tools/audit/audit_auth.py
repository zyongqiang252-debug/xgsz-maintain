# -*- coding: utf-8 -*-
"""审计第一轮：接口鉴权覆盖面（结果写 UTF-8 文本，便于阅读）"""
import json

import requests

BASE = "http://127.0.0.1:18080"
OUT_TXT = r"C:\Users\aaa\AppData\Local\Temp\xgsz-audit-auth.txt"
OUT_JSON = r"C:\Users\aaa\AppData\Local\Temp\xgsz-audit-auth.json"

lines = []


def w(s=""):
    lines.append(s)


s = requests.Session()
spec = requests.get(BASE + "/openapi.json", timeout=30).json()
paths = spec["paths"]
w(f"接口总数：{sum(len(v) for v in paths.values())}")

OPEN_OK = {"/health", "/", "/docs", "/openapi.json", "/redoc", "/favicon.ico"}
PUBLIC_AUTH = ("/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/send-code",
               "/api/v1/auth/reset-password", "/api/v1/auth/bind-phone")

rows = []
for path, methods in sorted(paths.items()):
    for method, op in methods.items():
        if method not in ("get", "post", "put", "delete", "patch"):
            continue
        declared = bool(op.get("security"))
        url = BASE + path
        for p in op.get("parameters", []):
            if p.get("in") == "path":
                url = url.replace("{" + p["name"] + "}", "999999")
        if "{" in url:
            continue
        try:
            if method in ("get", "delete"):
                r = s.request(method, url, timeout=25)
            else:
                r = s.request(method, url, json={}, timeout=25)
            code = r.status_code
        except Exception as e:
            code = f"ERR:{type(e).__name__}"
        rows.append((method.upper(), path, declared, code))

anon200 = [x for x in rows if x[3] == 200 and x[1] not in OPEN_OK]
w("\n## 匿名可访问且返回 200")
for m, p, d, c in anon200:
    tag = "（登录/注册类，应公开）" if p.startswith(PUBLIC_AUTH) else "★ 需确认"
    w(f"  {m:6} {p:58} {tag}")
w(f"  共 {len(anon200)} 个")

w("\n## 匿名 422（未走到鉴权，可能是公开接口或漏鉴权）")
for m, p, d, c in [x for x in rows if x[3] == 422]:
    w(f"  {m:6} {p:58} {'登录类（OK）' if p.startswith(PUBLIC_AUTH) else '★ 需确认'}")

from collections import Counter
w("\n## 状态码分布")
for k, v in Counter(x[3] for x in rows).most_common():
    w(f"  {k}: {v}")

w("\n## 未在 OpenAPI 声明 security 的接口（共 %d）" % len([x for x in rows if not x[2]]))
for m, p, d, c in rows:
    if not d:
        w(f"  {m:6} {p:58} 匿名 -> {c}")

open(OUT_TXT, "w", encoding="utf-8").write("\n".join(lines))
json.dump({"total": len(rows),
           "anon200": [{"m": m, "p": p} for m, p, d, c in anon200],
           "anon422": [{"m": m, "p": p} for m, p, d, c in rows if c == 422],
           "undeclared": [{"m": m, "p": p, "code": c} for m, p, d, c in rows if not d]},
          open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("done", OUT_TXT)

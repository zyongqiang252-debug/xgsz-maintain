# -*- coding: utf-8 -*-
"""静态审计：用 AST 找出所有 API 路由，标注是否带鉴权依赖"""
import ast
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

API_DIR = r"C:\Users\aaa\Desktop\xgsz-maintain\backend\app\api"
AUTH_HINTS = ("get_current_user", "get_optional_user", "require_admin", "require_supervisor",
              "require_roles", "require_manage", "_require_manage")

rows = []
for fn in sorted(os.listdir(API_DIR)):
    if not fn.endswith(".py"):
        continue
    path = os.path.join(API_DIR, fn)
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        decos = []
        for d in node.decorator_list:
            if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute):
                decos.append((d.func.attr, ast.unparse(d.args[0]) if d.args else ""))
        routes = [(m, p) for m, p in decos if m in ("get", "post", "put", "delete", "patch")]
        if not routes:
            continue
        params = [a.arg for a in node.args.args]
        # 依赖在 default 里：Depends(get_current_user) / Depends(require_admin)
        deps = []
        for d in node.args.defaults + [x for x in node.args.kw_defaults if x is not None]:
            if isinstance(d, ast.Call):
                s = ast.unparse(d)
                deps.append(s)
        body = ast.get_source_segment(src, node) or ""
        has_auth = any(h in " ".join(deps) for h in AUTH_HINTS)
        # 函数体内手动鉴权（如 _require_manage(current_user)）
        manual = "_require_manage(" in body or "require_admin(" in body or "require_supervisor(" in body
        for m, p in routes:
            rows.append({
                "file": fn, "method": m.upper(), "path": p.replace("'", "").replace('"', ""),
                "func": node.name, "auth_dep": has_auth, "manual_check": manual,
                "params": params,
            })

total = len(rows)
noauth = [r for r in rows if not r["auth_dep"] and not r["manual_check"]]
print(f"路由总数 {total}，无鉴权依赖 {len(noauth)} 个\n")
by_file = {}
for r in noauth:
    by_file.setdefault(r["file"], []).append(r)
for f, items in sorted(by_file.items(), key=lambda kv: -len(kv[1])):
    print(f"### {f}  ({len(items)})")
    for r in items:
        print(f"  {r['method']:6} {r['path']:50} {r['func']}")
    print()

out = os.path.join(os.environ["TEMP"], "xgsz-audit-routes.txt")
with open(out, "w", encoding="utf-8") as fh:
    fh.write(f"路由总数 {total}，无鉴权依赖 {len(noauth)}\n\n")
    for r in rows:
        flag = "AUTH" if (r["auth_dep"] or r["manual_check"]) else "OPEN"
        fh.write(f"{flag:5} {r['method']:6} {r['path']:55} {r['file']}::{r['func']}\n")
print("明细 ->", out)

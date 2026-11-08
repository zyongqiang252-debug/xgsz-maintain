# -*- coding: utf-8 -*-
"""审计第八轮：代码质量静态扫描"""
import io
import os
import re
import sys
from collections import Counter

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"C:\Users\aaa\Desktop\xgsz-maintain\backend\app"
OUT = r"C:\Users\aaa\AppData\Local\Temp\xgsz-audit-code.txt"

PATTERNS = {
    "裸 except（except: 或 except Exception: 后直接 pass）": re.compile(r"except[^:]*:\s*(#.*)?\n\s*pass\b"),
    "TODO / FIXME / HACK": re.compile(r"#\s*(TODO|FIXME|HACK|XXX)"),
    "f-string 拼 SQL": re.compile(r"(text|execute)\s*\(\s*f[\"']"),
    "print() 打印": re.compile(r"^\s*print\(", re.M),
    "datetime.utcnow()": re.compile(r"utcnow\(\)"),
    "硬编码密码/密钥": re.compile(r"(password|secret|token)\s*=\s*[\"'][^\"']{6,}[\"']", re.I),
    "verify=False（跳过证书校验）": re.compile(r"verify\s*=\s*False"),
    "eval()/exec()": re.compile(r"\b(eval|exec)\s*\("),
    "shell=True": re.compile(r"shell\s*=\s*True"),
    "except Exception: 后 return None 吞异常": re.compile(r"except Exception[^:]*:\s*(#.*)?\n\s*return None"),
}

hits = {k: [] for k in PATTERNS}
file_errors = []
py_files = []
for dirpath, _, files in os.walk(ROOT):
    for f in files:
        if f.endswith(".py"):
            py_files.append(os.path.join(dirpath, f))

total_lines = 0
for path in py_files:
    try:
        src = open(path, encoding="utf-8").read()
    except Exception as e:
        file_errors.append(f"{path}: {e}")
        continue
    total_lines += src.count("\n")
    rel = os.path.relpath(path, os.path.dirname(ROOT))
    for name, pat in PATTERNS.items():
        for m in pat.finditer(src):
            line_no = src[:m.start()].count("\n") + 1
            snippet = src.splitlines()[line_no - 1].strip()[:110]
            hits[name].append((rel, line_no, snippet))

lines = [f"Python 文件 {len(py_files)} 个，{total_lines} 行"]
for name, items in hits.items():
    lines.append(f"\n## {name}：{len(items)} 处")
    for rel, ln, sn in items[:12]:
        lines.append(f"  {rel}:{ln}  {sn}")
    if len(items) > 12:
        lines.append(f"  … 其余 {len(items)-12} 处")

# 文件大小 top
sizes = sorted(((os.path.relpath(p, os.path.dirname(ROOT)), os.path.getsize(p)) for p in py_files),
               key=lambda x: -x[1])[:8]
lines.append("\n## 最大的 Python 文件")
for rel, sz in sizes:
    lines.append(f"  {sz/1024:7.1f} KB  {rel}")

open(OUT, "w", encoding="utf-8").write("\n".join(lines))
print("\n".join(lines[:8]))
print("\n->", OUT)

# -*- coding: utf-8 -*-
"""把本地 master 推到 GitHub（自动判断有无写权限；没有就 fork 后推到自己的 fork）

背景：本机 git 的 TLS 直连不通，但走本地代理可以（Clash 127.0.0.1:7897）。
用法：
    # 1) 只看状态，不推送
    python tools\\push_to_github.py --dry-run

    # 2) 正式推送（token 从文件读，读完自动删）
    python tools\\push_to_github.py --token-file C:\\Users\\aaa\\Desktop\\gh_token.txt --delete-token-file

    # 3) 也可以走环境变量
    set GITHUB_TOKEN=ghp_xxx
    python tools\\push_to_github.py

token 权限：
    - classic PAT：勾 repo
    - fine-grained PAT：只选该仓库，Repository permissions -> Contents: Read and write
"""
import argparse
import os
import subprocess
import sys
import time
import urllib.parse

import requests

DEFAULT_REPO = "zyongqiang252-debug/xgsz-maintain"
DEFAULT_BRANCH = "master"
DEFAULT_PROXY = "http://127.0.0.1:7897"
REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_token(args):
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    src = "环境变量"
    if not tok and args.token_file and os.path.exists(args.token_file):
        with open(args.token_file, "r", encoding="utf-8-sig") as f:
            tok = f.read()
        src = args.token_file
    tok = tok.strip()
    if not tok:
        return None, None
    return tok, src


def git(*argv, check=True):
    r = subprocess.run(["git", *argv], cwd=REPO_DIR, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(argv)} 失败：\n{r.stderr or r.stdout}")
    return r.stdout.strip(), r.returncode


def api(session, url, method="GET", **kw):
    r = session.request(method, url, timeout=40, **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"_text": r.text[:300]}


def mask(text, token):
    return text.replace(token, "***") if token else text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=DEFAULT_REPO, help="owner/name，默认 zyongqiang252-debug/xgsz-maintain")
    ap.add_argument("--branch", default=DEFAULT_BRANCH)
    ap.add_argument("--token-file", default=os.path.join(os.path.expanduser("~"), "gh_token.txt"))
    ap.add_argument("--delete-token-file", action="store_true", help="推送成功后删除 token 文件")
    ap.add_argument("--proxy", default=DEFAULT_PROXY, help="git 走这个代理，传 '' 表示不走代理")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-fork", action="store_true", help="没有写权限时直接失败，不自动 fork")
    args = ap.parse_args()

    out, _ = git("rev-parse", "--abbrev-ref", "HEAD")
    print(f"本地分支：{out}")
    ahead, _ = git("log", "--oneline", "55ac2ef..HEAD")
    print("待推送提交：")
    for line in ahead.splitlines():
        print("  ", line)

    token, src = load_token(args)
    if not token:
        print("\n未找到 token。")
        print("  方式一：把 token 存到", args.token_file, "再跑本脚本")
        print("  方式二：set GITHUB_TOKEN=ghp_xxx 后再跑")
        return 2

    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                      "User-Agent": "xgsz-maintain-push"})
    if args.proxy:
        s.proxies.update({"https": args.proxy, "http": args.proxy})

    code, me = api(s, "https://api.github.com/user")
    if code != 200:
        print(f"\ntoken 无效（HTTP {code}）：{me}")
        return 3
    login = me["login"]
    print(f"\ntoken 有效，账号：{login}（来源：{src}）")

    code, repo = api(s, f"https://api.github.com/repos/{args.repo}")
    if code != 200:
        print(f"读仓库失败（HTTP {code}）：{repo}")
        return 4
    push_ok = bool((repo.get("permissions") or {}).get("push"))
    print(f"对 {args.repo} 的写权限：{'有' if push_ok else '无'}")

    target = args.repo
    if not push_ok:
        if args.no_fork:
            print("没有写权限，且指定了 --no-fork，退出。请让仓库管理员把 " + login + " 加为 collaborator。")
            return 5
        print(f"→ 自动 fork 到 {login}/{args.repo.split('/')[1]}")
        if not args.dry_run:
            code, fr = api(s, f"https://api.github.com/repos/{args.repo}/forks", method="POST", json={})
            if code not in (200, 201, 202):
                print(f"fork 失败（HTTP {code}）：{fr}")
                return 6
            for _ in range(20):
                time.sleep(3)
                code, chk = api(s, f"https://api.github.com/repos/{login}/{args.repo.split('/')[1]}")
                if code == 200:
                    break
            else:
                print("fork 尚未就绪，稍后重试本脚本即可（fork 已在后台创建）")
                return 7
        target = f"{login}/{args.repo.split('/')[1]}"

    if args.dry_run:
        print(f"\n[dry-run] 将推送到：{target} 分支 {args.branch}")
        return 0

    proxy_args = ["-c", f"http.proxy={args.proxy}"] if args.proxy else []
    url = f"https://x-access-token:{token}@github.com/{target}.git"
    print(f"\n推送 → {target} ({args.branch}) ...")
    r = subprocess.run(["git", *proxy_args, "push", url, f"{args.branch}:{args.branch}"],
                       cwd=REPO_DIR, capture_output=True, text=True, encoding="utf-8", errors="replace")
    combined = mask((r.stdout or "") + (r.stderr or ""), token)

    if r.returncode == 0:
        # 顺手把 origin 指回真实地址（不带 token），方便以后 fetch
        git("remote", "set-url", "origin", f"https://github.com/{target}.git", check=False)
        print("推送成功：")
        print(combined.strip())
        code, head = api(s, f"https://api.github.com/repos/{target}/commits/{args.branch}")
        if code == 200:
            print(f"远端 HEAD：{head['sha'][:12]}  {head['commit']['message'].splitlines()[0]}")
        if target != args.repo:
            print("\n这是你的 fork。要并回主仓库，去开 PR：")
            print(f"  https://github.com/{args.repo}/compare/{args.branch}...{login}:{args.branch}?expand=1")
        else:
            print(f"\n仓库地址：https://github.com/{args.repo}")
        if args.delete_token_file and src == args.token_file and os.path.exists(args.token_file):
            os.remove(args.token_file)
            print(f"已删除 token 文件：{args.token_file}")
    else:
        print("推送失败：")
        print(combined.strip())
        return 8
    return 0


if __name__ == "__main__":
    sys.exit(main())

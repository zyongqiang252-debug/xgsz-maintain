# -*- coding: utf-8 -*-
"""下载并解压便携版 PostgreSQL 16（Windows amd64，来自 Maven Central 的 zonky 构建）"""
import io
import os
import sys
import tarfile
import urllib.request
import zipfile

VERSION = "16.2.0"
JAR = (f"https://repo1.maven.org/maven2/io/zonky/test/postgres/"
       f"embedded-postgres-binaries-windows-amd64/{VERSION}/"
       f"embedded-postgres-binaries-windows-amd64-{VERSION}.jar")
ROOT = r"C:\Users\aaa\AppData\Local\xgsz-runtime"
PKG = os.path.join(ROOT, "pgsql")
CACHE = os.path.join(ROOT, "cache")


def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 1_000_000:
        print("已缓存:", dest)
        return dest
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    print("下载:", url)
    with urllib.request.urlopen(url, timeout=120) as r, open(dest + ".part", "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if total:
                print(f"\r  {got/1048576:.1f}/{total/1048576:.1f} MB", end="", flush=True)
    print()
    os.replace(dest + ".part", dest)
    return dest


def main():
    jar = download(JAR, os.path.join(CACHE, f"pg-{VERSION}.jar"))
    with zipfile.ZipFile(jar) as z:
        names = [n for n in z.namelist() if n.endswith(".txz")]
        print("jar 内资源:", names)
        txz = names[0]
        data = z.read(txz)
    os.makedirs(PKG, exist_ok=True)
    print(f"解压 {txz} -> {PKG}")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as tar:
        members = tar.getmembers()
        print("条目数:", len(members))
        tar.extractall(PKG, filter="data")
    exe = os.path.join(PKG, "bin", "postgres.exe")
    print("postgres.exe 存在:", os.path.exists(exe))
    return 0 if os.path.exists(exe) else 1


if __name__ == "__main__":
    sys.exit(main())

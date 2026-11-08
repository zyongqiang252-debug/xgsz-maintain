# -*- coding: utf-8 -*-
"""建库：确保 xgsz_maintain 存在（PG 便携版没有 psql，只能用驱动连 postgres 库建）"""
import psycopg2

conn = psycopg2.connect(host="localhost", port=15432, user="admin", dbname="postgres")
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute("SELECT 1 FROM pg_database WHERE datname = 'xgsz_maintain'")
    if cur.fetchone():
        print("数据库已存在")
    else:
        cur.execute("CREATE DATABASE xgsz_maintain")
        print("数据库已创建")
with conn.cursor() as cur:
    cur.execute("SELECT version()")
    print(cur.fetchone()[0])
conn.close()

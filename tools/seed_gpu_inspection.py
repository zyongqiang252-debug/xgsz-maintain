r"""GPU 机房巡检模板 + 保养计划种子

用法（backend 目录）：
    .\.venv\Scripts\python.exe ..\tools\seed_gpu_inspection.py
"""
import io
import json
import sys
from datetime import datetime, timedelta

import psycopg2

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
DSN = dict(host="localhost", port=15432, user="admin", dbname="xgsz_maintain")

TEMPLATES = [
    {
        "name": "GPU 服务器日常巡检表",
        "device_type": "GPU服务器整机",
        "items": [
            {"name": "GPU 数量识别", "standard": "nvidia-smi -L 与配置一致（8 张）", "type": "check"},
            {"name": "GPU 温度", "standard": "满载 ≤ 80℃，空闲 ≤ 50℃", "type": "number"},
            {"name": "进风温度", "standard": "≤ 27℃（ipmitool sensor）", "type": "number"},
            {"name": "风扇转速", "standard": "全部正常运转，无 0 转速", "type": "check"},
            {"name": "ECC 错误计数", "standard": "CE 无增长，UCE = 0", "type": "number"},
            {"name": "驱动 / CUDA 版本", "standard": "与基线一致（如 550.54.15 / 12.4）", "type": "check"},
            {"name": "GPU 固件版本", "standard": "同批次一致，无回退", "type": "check"},
            {"name": "电源模块状态", "standard": "PSU 全绿，无告警", "type": "check"},
            {"name": "IB 链路状态", "standard": "ibstat 端口 Active，速率达标", "type": "check"},
            {"name": "磁盘阵列状态", "standard": "无降级/重建", "type": "check"},
        ],
    },
    {
        "name": "机房环境巡检表",
        "device_type": "GPU服务器整机",
        "items": [
            {"name": "机房温度", "standard": "18~27℃", "type": "number"},
            {"name": "机房湿度", "standard": "40%~60%", "type": "number"},
            {"name": "空调运行状态", "standard": "制冷正常，无告警", "type": "check"},
            {"name": "机柜前后风道", "standard": "无遮挡，防尘网清洁", "type": "check"},
            {"name": "PDU / UPS", "standard": "供电正常，无跳闸记录", "type": "check"},
            {"name": "线缆与光模块", "standard": "无松动、无折损、无异味", "type": "check"},
        ],
    },
]

PLANS = [
    # (plan_name, items, cycle_days, device_code)
    ("GPU 固件与驱动季度核查",
     "1. 核对 GPU VBIOS / BMC 固件版本\n2. 对比基线版本清单\n3. 记录差异并评估升级窗口", 90, "GPU-SRV-001"),
    ("GPU 节点半年除尘与散热检查",
     "1. 停机断电，清理防尘网与散热翅片\n2. 检查风扇转速与异响\n3. 检查导热硅脂状态", 180, "GPU-SRV-001"),
    ("训练集群 02 季度固件核查",
     "1. 核对 A100 节点固件版本\n2. 驱动/CUDA 版本一致性检查", 90, "GPU-SRV-002"),
]


def ins(cur, table, cols, vals):
    ph = ",".join(["%s"] * len(vals))
    cur.execute(f"insert into {table}({','.join(cols)}, created_at, updated_at) values ({ph}, now(), now())", vals)


def ins_json(cur, table, cols, vals):
    """JSONB 字段需要 Json 包装"""
    from psycopg2.extras import Json
    vals = [Json(v) if isinstance(v, (list, dict)) else v for v in vals]
    ph = ",".join(["%s"] * len(vals))
    cur.execute(f"insert into {table}({','.join(cols)}, created_at, updated_at) values ({ph}, now(), now())", vals)


def main():
    c = psycopg2.connect(**DSN)
    cur = c.cursor()

    # 1) 点检模板
    # 先清点检记录（外键），再清模板
    cur.execute("delete from inspection_records")
    cur.execute("delete from inspection_templates")
    for t in TEMPLATES:
        ins_json(cur, "inspection_templates", ["name", "device_type", "items", "active"],
                 [t["name"], t["device_type"], t["items"], True])
    print(f"点检模板：{len(TEMPLATES)} 个（GPU 日常巡检 {len(TEMPLATES[0]['items'])} 项 / 机房环境 {len(TEMPLATES[1]['items'])} 项）")

    # 2) 保养计划
    cur.execute("select id, device_code from devices")
    dev_map = {code: did for did, code in cur.fetchall()}
    cur.execute("select id, real_name from users where role='ADMIN' order by id limit 1")
    row = cur.fetchone()
    admin_id, admin_name = (row if row else (None, "系统管理员"))

    cur.execute("delete from maintenance_records")
    cur.execute("delete from maintenance_plans")
    now = datetime.now()
    for name, items, cycle, code in PLANS:
        ins(cur, "maintenance_plans",
            ["plan_name", "device_id", "device_code", "items", "cycle_type", "cycle_value",
             "next_due_at", "responsible_id", "responsible_name", "status"],
            [name, dev_map.get(code), code, items, "DAYS", cycle,
             now + timedelta(days=cycle), admin_id, admin_name, "ACTIVE"])
    print(f"保养计划：{len(PLANS)} 条（固件季度核查 + 半年除尘）")

    c.commit()
    c.close()
    print("\n完成：巡检模板与保养计划已切换为 GPU 机房语境")


if __name__ == "__main__":
    main()

r"""把领域字典从「工厂设备维修」换成「GPU 服务器维修」

用法（backend 目录）：
    .\.venv\Scripts\python.exe ..\tools\seed_gpu_domain.py

说明：
- 只改字典/示例数据，不动表结构（字段扩展另做迁移）
- devices 用 UPDATE 而非 DELETE，避免工单外键断裂
- 可重复执行（先清后插）
"""
import io
import sys

import psycopg2
from psycopg2.extras import Json

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DSN = dict(host="localhost", port=15432, user="admin", dbname="xgsz_maintain")

DEVICE_TYPES = [
    ("GPU服务器整机", "GPU-SRV"),
    ("GPU模组/板卡", "GPU-MOD"),
    ("计算节点", "COMPUTE"),
    ("存储节点", "STORAGE"),
    ("IB/网络交换机", "IB-SW"),
    ("管理节点", "MGMT"),
]
FAULT_TYPES = [
    ("GPU硬件故障", "GPU-HW"),
    ("显存/ECC错误", "GPU-MEM"),
    ("温度/散热故障", "THERMAL"),
    ("供电故障", "POWER"),
    ("NVLink/互联故障", "NVLINK"),
    ("驱动/CUDA故障", "SOFTWARE"),
    ("网络故障(IB/RoCE)", "NETWORK"),
    ("主板/CPU/内存故障", "BOARD"),
    ("存储/硬盘故障", "DISK"),
    ("固件/BMC故障", "FIRMWARE"),
]
KNOWLEDGE_TYPES = [
    ("故障诊断", "DIAGNOSIS"),
    ("处置方案", "SOLUTION"),
    ("巡检保养", "PREVENTIVE"),
    ("固件升级", "FIRMWARE-OPS"),
]

PHENOMENA = {
    "GPU硬件故障": [
        ("GPU掉卡/无法识别", "nvidia-smi 看不到卡，或 lspci 无法枚举"),
        ("Xid 报错", "dmesg 出现 NVRM: Xid 错误码"),
        ("GPU 降频/性能下降", "SM 时钟被限制，算力低于基线"),
    ],
    "显存/ECC错误": [
        ("ECC 可纠正错误(CE)激增", "nvidia-smi -q 中 ECC 计数持续增长"),
        ("ECC 不可纠正错误(UCE)", "业务进程报 CUDA error: uncorrectable ECC"),
        ("显存容量异常", "可用显存小于标称值"),
    ],
    "温度/散热故障": [
        ("GPU 温度过高", "温度超过 85℃ 触发降频或关机"),
        ("风扇转速异常", "风扇转速 0 或持续满载"),
        ("机箱进风温度高", "机房热点，进风温度超出规格"),
    ],
    "供电故障": [
        ("电源模块故障", "PSU 指示灯异常 / BMC 报电源故障"),
        ("供电不足/掉电", "高负载时整机重启"),
    ],
    "NVLink/互联故障": [
        ("NVLink 降速/断开", "nvlink 状态非 Active 或带宽下降"),
        ("GPU 间通信超时", "NCCL 测试超时 / all-reduce 失败"),
    ],
    "驱动/CUDA故障": [
        ("驱动加载失败", "nvidia-smi 报 driver/library version mismatch"),
        ("CUDA 版本不匹配", "程序报 CUDA driver version is insufficient"),
        ("nvidia-smi 无响应", "命令挂起或返回 Failed to initialize NVML"),
    ],
    "网络故障(IB/RoCE)": [
        ("IB 链路降速", "ibstat 速率低于预期"),
        ("光模块告警", "光功率异常 / 模块温度高"),
        ("丢包/重传", "perftest 带宽不达标"),
    ],
    "主板/CPU/内存故障": [
        ("内存 CE/UE", "EDAC 报内存错误"),
        ("CPU 降频", "CPU 频率被限制"),
        ("BMC 无法登录", "带外管理地址不通"),
    ],
    "存储/硬盘故障": [
        ("硬盘掉盘", "系统日志出现 offline/removed"),
        ("RAID 降级", "阵列降级或重建中"),
    ],
    "固件/BMC故障": [
        ("固件版本不一致", "同批次机器 GPU/BMC 固件版本不同"),
        ("BMC 异常重启", "带外管理频繁断连"),
    ],
}

ROOT_CAUSES = {
    "硬件老化/损坏": [
        ("显存颗粒损坏", "显存坏块导致 Xid 48/63"),
        ("供电模块电容老化", "PSU 输出不稳"),
        ("风扇轴承磨损", "转速异常或异响"),
    ],
    "散热不良": [
        ("机房温度超标", "进风温度高于 27℃"),
        ("风道堵塞/积灰", "散热翅片积灰严重"),
        ("导热硅脂干涸", "GPU 核心与散热器接触不良"),
    ],
    "供电问题": [
        ("PDU 供电不稳", "机柜供电波动"),
        ("电源冗余失效", "单路供电故障"),
    ],
    "固件/驱动缺陷": [
        ("驱动版本兼容性问题", "升级后出现掉卡"),
        ("GPU 固件不匹配", "VBIOS 与整机不匹配"),
        ("BMC 固件缺陷", "带外管理异常"),
    ],
    "人为操作": [
        ("误操作/误拔卡", "维护时未断电插拔"),
        ("配置错误", "BIOS/固件参数配错"),
        ("未按规范升级", "跳版本升级导致异常"),
    ],
    "环境/外部因素": [
        ("网络设备故障", "上游交换机端口异常"),
        ("机房断电/晃电", "非计划断电"),
        ("静电/震动", "运输或维护造成损伤"),
    ],
}

FAULT_CODES = [
    ("XID-13", "GPU 显存 ECC 可纠正错误（CE），通常可继续运行但需关注", "GPU服务器整机"),
    ("XID-31", "GPU 内存页错误/非法地址访问，多为应用或驱动问题", "GPU服务器整机"),
    ("XID-43", "GPU 停止处理任务，需要复位 GPU 或重启节点", "GPU服务器整机"),
    ("XID-48", "双比特 ECC 错误（不可纠正），显存硬件故障，需换卡", "GPU服务器整机"),
    ("XID-62", "GPU 内部微控制器错误，通常需复位或更换", "GPU服务器整机"),
    ("XID-63", "GPU 行重映射失败，显存坏块，需 RMA", "GPU服务器整机"),
    ("XID-74", "NVLink 链路错误", "GPU服务器整机"),
    ("XID-79", "GPU 已从总线移除（掉卡），常见于供电/散热/硬件故障", "GPU服务器整机"),
    ("XID-94", "GPU 容器/虚拟化相关错误", "GPU服务器整机"),
    ("XID-95", "GPU 未授权或固件异常", "GPU服务器整机"),
    ("ECC-CE", "显存可纠正错误计数超过阈值", "GPU服务器整机"),
    ("ECC-UE", "显存不可纠正错误，进程将失败", "GPU服务器整机"),
    ("NVML-ERR", "nvidia-smi 无法初始化 NVML（驱动未加载/掉卡）", "GPU服务器整机"),
    ("IB-LINK-DOWN", "IB 端口链路 down，检查光模块与交换机端口", "IB/网络交换机"),
    ("PSU-FAIL", "电源模块故障，BMC 报 PSU 异常", "GPU服务器整机"),
    ("BMC-UNREACH", "BMC 带外管理地址不可达", "GPU服务器整机"),
]

SPARE_PARTS = [
    ("GPU-A100-80G", "A100 80G GPU 卡", "SXM4/80GB HBM2e", "张", 2, 1, 95000, "GPU服务器整机", "备件库A-01", "NVIDIA"),
    ("GPU-H100-80G", "H100 80G GPU 卡", "SXM5/80GB HBM3", "张", 2, 1, 220000, "GPU服务器整机", "备件库A-02", "NVIDIA"),
    ("MEM-DDR5-64G", "服务器内存 64G DDR5", "RDIMM 4800MHz", "条", 16, 8, 2600, "GPU服务器整机", "备件库B-01", "三星"),
    ("PSU-3000W", "3000W 电源模块", "冗余热插拔", "个", 4, 2, 4800, "GPU服务器整机", "备件库B-02", "台达"),
    ("FAN-MODULE", "服务器风扇模组", "8cm 高转速", "个", 10, 4, 320, "GPU服务器整机", "备件库B-03", "Nidec"),
    ("IB-HCA-200G", "200G IB 网卡", "HDR/HCA", "张", 4, 2, 12000, "IB/网络交换机", "备件库C-01", "Mellanox"),
    ("OPTIC-400G", "400G 光模块", "QSFP-DD SR8", "个", 8, 4, 6800, "IB/网络交换机", "备件库C-02", "Mellanox"),
    ("SSD-NVME-3.84T", "3.84T NVMe SSD", "U.2 企业级", "块", 6, 2, 4200, "存储节点", "备件库D-01", "三星"),
    ("HEATSINK-GPU", "GPU 散热器", "SXM 冷板/风冷", "个", 3, 1, 5600, "GPU服务器整机", "备件库A-03", "原厂"),
]

DEVICES = [
    ("GPU-SRV-001", "计算集群 01 号节点", "GPU-SRV", "DGX H100（8×H100）", "NVIDIA", "机房A / 机柜A03 / U12-U19"),
    ("GPU-SRV-002", "训练集群 02 号节点", "GPU-SRV", "8×A100 80G 服务器", "浪潮", "机房A / 机柜A04 / U08-U15"),
    ("IB-SW-001", "IB 骨干交换机 01", "IB-SW", "MQM9700 400G", "Mellanox", "机房A / 机柜A01 / U40"),
]

KNOWLEDGE = [
    ("Xid 79 GPU 掉卡（从总线移除）排查与处置", "xid-79", "GPU服务器整机", """## 故障现象
业务进程报 CUDA error: unknown error；nvidia-smi 中该卡消失或显示 ERR!；dmesg 出现
NVRM: Xid (PCI:0000:3b:00): 79, GPU has fallen off the bus。

## 排查步骤
1. nvidia-smi -q 确认卡是否还在枚举
2. lspci | grep -i nvidia 看 PCIe 设备是否可见
3. dmesg -T | grep -iE "xid|nvrm|pcie" 查看错误上下文
4. ipmitool sel list 查 BMC 是否有电源/温度事件
5. nvidia-smi -q -d TEMPERATURE 看近期温度曲线

## 处置方案
1. 先软复位：nvidia-smi --gpu-reset -i <index>；不行则重启节点
2. 复位后仍掉卡 → 检查供电（PSU 报错 / PDU 供电）与散热（风扇 / 积灰）
3. 供电散热正常仍复现 → 判定 GPU 硬件故障，走 RMA 换卡
4. 换卡后跑 gpu-burn 300 与 dcgmi diag -r 3 验证"""),

    ("显存 ECC 错误激增（CE/UCE）判定与处理", "ecc", "GPU服务器整机", """## 故障现象
nvidia-smi -q -d ECC 中 Single Bit 计数快速上涨；严重时出现 Double Bit 错误，业务进程直接失败。

## 判定标准
- CE（可纠正）：单卡单日增长 > 100 或持续线性增长 → 记录并观察
- UCE（不可纠正）：出现即判定显存硬件问题，需换卡

## 处置
1. 记录基线：nvidia-smi -q -d ECC > /tmp/ecc_$(date +%F).log
2. CE 激增：先排除温度（>80℃ 会放大错误率），降载观察 24h
3. UCE：立即隔离该卡，业务切走，提交 RMA
4. 更换后复核：dcgmi diag -r 2 + 连续 24h ECC 计数为 0"""),

    ("GPU 温度过高导致降频的排查", "thermal", "GPU服务器整机", """## 故障现象
nvidia-smi 显示温度 85℃+，SM 时钟明显低于基线，训练吞吐下降；BMC 可能记录过热事件。

## 排查
1. nvidia-smi -q -d TEMPERATURE,CLOCK 看温度与降频原因（SW/HW Thermal Slowdown）
2. 机房环境：进风温度是否 > 27℃（ipmitool sensor | grep -i inlet）
3. 风道：前后是否有遮挡、防尘网是否堵塞、风扇转速是否正常
4. 单卡异常高温（显著高于同机其他卡）→ 散热器接触问题

## 处置
1. 环境问题：调整机房空调/机柜风道，清理防尘网
2. 风扇故障：更换风扇模组
3. 单卡高温：重涂导热硅脂或更换散热器；仍高温则 RMA
4. 临时缓解：nvidia-smi -pl <瓦数> 限功耗，避免业务中断"""),

    ("IB 链路降速 / NCCL 通信超时的定位", "ib", "IB/网络交换机", """## 故障现象
多机训练 NCCL timeout，all-reduce 带宽远低于基线；ibstat 显示速率 100Gb/s（应为 400Gb/s）或 State 非 Active。

## 排查
1. ibstat / iblinkinfo 看端口 State、Rate、物理错误计数
2. perftest（ib_write_bw）单链路打流，定位慢链路
3. 光模块：mlxlink -d <dev> 查光功率、温度、FEC 计数
4. 交换机侧：对应端口是否有 CRC 错误、是否被降速

## 处置
1. 重插/更换光模块与光纤（优先怀疑光模块）
2. 交换机端口换口验证，排除端口故障
3. 固件/驱动不一致的节点统一版本
4. 恢复后跑 nccl-tests 全互联验证带宽"""),
]


def ins(cur, table, cols, vals):
    """插入并自动补 created_at/updated_at（BaseModel 要求非空）"""
    ph = ",".join(["%s"] * len(vals))
    sql = f"insert into {table}({','.join(cols)}, created_at, updated_at) values ({ph}, now(), now())"
    cur.execute(sql, vals)


def main():
    c = psycopg2.connect(**DSN)
    cur = c.cursor()

    # 1) 分类字典
    cur.execute("delete from categories")
    for i, (name, code) in enumerate(DEVICE_TYPES, 1):
        ins(cur, "categories", ["name", "code", "category_type", "sort_order"], [name, code, "DEVICE_TYPE", i])
    for i, (name, code) in enumerate(FAULT_TYPES, 1):
        ins(cur, "categories", ["name", "code", "category_type", "sort_order"], [name, code, "FAULT_TYPE", i])
    for i, (name, code) in enumerate(KNOWLEDGE_TYPES, 1):
        ins(cur, "categories", ["name", "code", "category_type", "sort_order"], [name, code, "KNOWLEDGE_TYPE", i])
    print(f"分类：{len(DEVICE_TYPES)} 设备类型 + {len(FAULT_TYPES)} 故障类型 + {len(KNOWLEDGE_TYPES)} 知识类型")

    # 2) 故障现象级联
    cur.execute("delete from fault_phenomenon_categories")
    order = 0
    for parent, children in PHENOMENA.items():
        order += 1
        cur.execute("insert into fault_phenomenon_categories(parent_id, name, description, sort_order, created_at, updated_at) "
                    "values (NULL,%s,NULL,%s,now(),now()) returning id", (parent, order))
        pid = cur.fetchone()[0]
        for j, (name, desc) in enumerate(children, 1):
            ins(cur, "fault_phenomenon_categories", ["parent_id", "name", "description", "sort_order"],
                [pid, name, desc, j])
    print(f"故障现象：{len(PHENOMENA)} 大类 / {sum(len(v) for v in PHENOMENA.values())} 细项")

    # 3) 根本原因级联
    cur.execute("delete from root_cause_categories")
    order = 0
    for parent, children in ROOT_CAUSES.items():
        order += 1
        cur.execute("insert into root_cause_categories(parent_id, name, sort_order, created_at, updated_at) "
                    "values (NULL,%s,%s,now(),now()) returning id", (parent, order))
        pid = cur.fetchone()[0]
        for j, (name, desc) in enumerate(children, 1):
            ins(cur, "root_cause_categories", ["parent_id", "name", "description", "sort_order"],
                [pid, name, desc, j])
    print(f"根本原因：{len(ROOT_CAUSES)} 大类 / {sum(len(v) for v in ROOT_CAUSES.values())} 细项")

    # 4) 故障码（Xid）
    cur.execute("delete from fault_code_mappings")
    for code, desc, dtype in FAULT_CODES:
        ins(cur, "fault_code_mappings", ["fault_code", "fault_description", "device_type", "source"],
            [code, desc, dtype, "seed"])
    print(f"故障码：{len(FAULT_CODES)} 条（Xid / ECC / IB / PSU）")

    # 5) 备件
    cur.execute("delete from stock_movements")
    cur.execute("delete from spare_parts")
    for (code, name, spec, unit, stock, safety, price, dtype, loc, supplier) in SPARE_PARTS:
        ins(cur, "spare_parts",
            ["part_code", "part_name", "specification", "unit", "stock_quantity",
             "safety_stock", "unit_price", "device_type", "location", "supplier"],
            [code, name, spec, unit, stock, safety, price, dtype, loc, supplier])
    print(f"备件：{len(SPARE_PARTS)} 条（GPU 卡/内存/电源/风扇/IB 网卡/光模块/SSD）")

    # 6) 设备（UPDATE 保留 id）
    cur.execute("select id from devices order by id")
    ids = [r[0] for r in cur.fetchall()]
    for idx, dev in enumerate(DEVICES):
        code, name, dtype, model, mfr, loc = dev
        if idx < len(ids):
            cur.execute("update devices set device_code=%s, device_name=%s, device_type=%s, model=%s, "
                        "manufacturer=%s, location=%s where id=%s",
                        (code, name, dtype, model, mfr, loc, ids[idx]))
        else:
            ins(cur, "devices", ["device_code", "device_name", "device_type", "model", "manufacturer",
                                 "location", "run_status", "status_source"],
                [code, name, dtype, model, mfr, loc, "UNKNOWN", "manual"])
    print(f"设备：{len(DEVICES)} 台（GPU 服务器 + IB 交换机）")

    # 7) 知识库
    cur.execute("delete from knowledge_items")
    for title, tag, dtype, content in KNOWLEDGE:
        ins(cur, "knowledge_items", ["title", "content", "device_type", "fault_code", "status",
                                     "source_type", "version", "fault_tags"],
            [title, content, dtype, tag, "PUBLISHED", "seed", 1, Json([tag])])
    print(f"知识库：{len(KNOWLEDGE)} 条 GPU 实战案例")

    # 8) 历史工单分类映射到新体系
    mapping = {
        "机械故障": "GPU硬件故障", "电气故障": "供电故障", "液压故障": "温度/散热故障",
        "气动故障": "温度/散热故障", "控制故障": "驱动/CUDA故障", "传感故障": "主板/CPU/内存故障",
    }
    for old, new in mapping.items():
        cur.execute("update work_orders set fault_category=%s where fault_category=%s", (new, old))

    c.commit()
    c.close()
    print("\n完成：领域字典已切换为「GPU 服务器维修」")


if __name__ == "__main__":
    main()

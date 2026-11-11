"""报修文本的轻量故障分类：不要求报修人先选部位，提交后自动打大类标签。"""


def classify_fault(text, fault_object=None):
    s = f"{text or ''} {fault_object or ''}".strip().lower()
    if not s:
        return "其他"
    if any(k in s for k in ("gpu", "cuda", "nvidia", "xid", "显卡", "显存", "掉卡")):
        return "GPU"
    if any(k in s for k in ("集群", "cluster", "slurm", "k8s", "kubernetes", "调度", "训练任务", "作业")):
        return "集群"
    if any(k in s for k in ("网络", "交换机", "switch", "infiniband", "roce", "光模块", "链路", "端口", "丢包", "延迟", "down", " ib ")):
        return "网络"
    if any(k in s for k in ("硬盘", "磁盘", "ssd", "nvme", "掉盘", "存储", "raid", "ceph", "容量")):
        return "存储"
    if any(k in s for k in ("电源", "供电", "断电", "psu", "电压", "电流", "跳闸")):
        return "供电"
    return "其他"

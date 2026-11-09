"""工单状态分组：对外 6 个业务状态，内部保留过程痕迹

11 个原始状态对使用者太细，界面统一按 6 组展示：
  草稿 DRAFT
  待派工 SUBMITTED
  处理中 ASSIGNED / ACCEPTED / ARRIVED / INSPECTING / IN_PROGRESS
  待归档 ARCHIVING / COMPLETED（历史值）
  已归档 ARCHIVED
  已退回 REJECTED
原始状态仍写库，用于进度时间线与追溯；列表、筛选、导出、PDF 一律用分组名。
"""

DRAFT = "DRAFT"
SUBMITTED = "SUBMITTED"
PROCESSING = "PROCESSING"
ARCHIVING = "ARCHIVING"
ARCHIVED = "ARCHIVED"
REJECTED = "REJECTED"

PROCESSING_STATUSES = ("ASSIGNED", "ACCEPTED", "ARRIVED", "INSPECTING", "IN_PROGRESS")

GROUPS = {
    DRAFT: {"label": "草稿", "desc": "已建单未提交，可修改或删除", "color": "#6B7280"},
    SUBMITTED: {"label": "待派工", "desc": "已提交报修，等待派单或维修员领取", "color": "#D25F00"},
    PROCESSING: {"label": "处理中", "desc": "已派单/已接单/已到场/检查中/维修中，统一视为处理中", "color": "#2478D9"},
    ARCHIVING: {"label": "待归档", "desc": "维修完成，补齐 6 项字段后归档", "color": "#A16207"},
    ARCHIVED: {"label": "已归档", "desc": "已结案，只读，可打印 PDF", "color": "#86909C"},
    REJECTED: {"label": "已退回", "desc": "派单被退回或工单作废", "color": "#D32029"},
}

ORDER = [DRAFT, SUBMITTED, PROCESSING, ARCHIVING, ARCHIVED, REJECTED]

# 原始状态 -> 分组
_RAW_TO_GROUP = {
    "DRAFT": DRAFT,
    "SUBMITTED": SUBMITTED,
    "ASSIGNED": PROCESSING,
    "ACCEPTED": PROCESSING,
    "ARRIVED": PROCESSING,
    "INSPECTING": PROCESSING,
    "IN_PROGRESS": PROCESSING,
    "ARCHIVING": ARCHIVING,
    "COMPLETED": ARCHIVING,   # 历史值：修完待归档
    "ARCHIVED": ARCHIVED,
    "REJECTED": REJECTED,
}


def group_of(status) -> str:
    """原始状态（字符串或枚举）转分组"""
    if status is None:
        return ""
    raw = status.value if hasattr(status, "value") else str(status)
    return _RAW_TO_GROUP.get(raw.upper(), raw.upper())


def statuses_of(group: str):
    """分组下所有原始状态（用于 SQL IN 过滤）"""
    from app.models.work_order import WorkOrderStatus

    g = (group or "").upper()
    mapping = {
        DRAFT: [WorkOrderStatus.DRAFT.value],
        SUBMITTED: [WorkOrderStatus.SUBMITTED.value],
        PROCESSING: [getattr(WorkOrderStatus, s).value for s in PROCESSING_STATUSES],
        ARCHIVING: [WorkOrderStatus.ARCHIVING.value, WorkOrderStatus.COMPLETED.value],
        ARCHIVED: [WorkOrderStatus.ARCHIVED.value],
        REJECTED: [WorkOrderStatus.REJECTED.value],
    }
    return mapping.get(g, [])


def label_of(status) -> str:
    g = group_of(status)
    return GROUPS.get(g, {}).get("label", g)


def options():
    """给前端下拉/图例用的有序列表"""
    return [{"value": g, **GROUPS[g]} for g in ORDER]

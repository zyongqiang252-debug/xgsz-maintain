VALID_PRIORITIES = {"CRITICAL", "HIGH", "MEDIUM", "LOW"}


def normalize_priority(value, default="MEDIUM"):
    """把前端/客户传入的影响程度规范化为优先级；非法值降级为默认值。"""
    v = (value or "").strip().upper()
    return v if v in VALID_PRIORITIES else default

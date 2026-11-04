"""导入校验：Excel / PDF / 图片 OCR 三条导入链路共用

校验内容：
1. 工单号唯一性（库内已存在 → 警告）
2. 设备编码匹配设备库（匹配则回填 device_id，否则警告）
3. 维修员 / 报修人匹配系统用户（匹配则回填 id，否则警告）
"""
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.device import Device
from app.models.user import User
from app.models.work_order import WorkOrder


def validate_extracted(
    db: Session,
    extracted: Dict,
    seen_work_order_nos: Optional[set] = None,
) -> Tuple[Dict, List[str]]:
    """校验并补全抽取结果，返回 (补全后的字段, 警告列表)

    seen_work_order_nos: 同一批次内已出现的工单号集合，用于识别文件内重复。
    """
    data = dict(extracted or {})
    warnings: List[str] = []

    wo_no = str(data.get("work_order_no") or "").strip()
    if wo_no:
        if seen_work_order_nos is not None:
            if wo_no in seen_work_order_nos:
                warnings.append(f"工单号 {wo_no} 在本批次内重复")
            else:
                seen_work_order_nos.add(wo_no)
        if db.query(WorkOrder).filter(WorkOrder.work_order_no == wo_no).first():
            warnings.append(f"工单号 {wo_no} 已存在于系统")
    else:
        warnings.append("未填写工单号，确认时将自动生成")

    device_code = str(data.get("device_code") or "").strip()
    if device_code:
        dev = db.query(Device).filter(Device.device_code == device_code).first()
        if dev:
            data["device_id"] = dev.id
            if not data.get("device_name"):
                data["device_name"] = dev.device_name
        else:
            warnings.append(f"设备编码 {device_code} 未在设备库找到")
    else:
        warnings.append("未填写设备编码")

    for key, label in (("technician_name", "维修员"), ("reporter_name", "报修人")):
        name = str(data.get(key) or "").strip()
        if name:
            u = db.query(User).filter(User.real_name == name).first()
            if u:
                data[f"{key.replace('_name', '')}_id"] = u.id
            else:
                warnings.append(f"{label}「{name}」未匹配到系统用户")

    return data, warnings

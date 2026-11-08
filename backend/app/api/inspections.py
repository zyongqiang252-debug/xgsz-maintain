"""点检/巡检 API：模板管理、提交点检、异常一键转工单"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user, require_supervisor
from app.models.device import Device
from app.models.maintenance import InspectionRecord, InspectionTemplate
from app.models.user import User
from app.models.work_order import WorkOrder, WorkOrderStatus

router = APIRouter(tags=["点检巡检"], dependencies=[Depends(get_current_user)])


class TemplateItem(BaseModel):
    name: str
    standard: Optional[str] = None
    type: Optional[str] = "check"   # check / number


class TemplateIn(BaseModel):
    name: str = Field(..., max_length=200)
    device_type: Optional[str] = None
    items: List[TemplateItem]
    active: bool = True


class ResultItem(BaseModel):
    name: str
    ok: bool = True
    value: Optional[str] = None
    remark: Optional[str] = None


class RecordIn(BaseModel):
    template_id: int
    device_code: str
    results: List[ResultItem]
    remark: Optional[str] = None
    create_work_order_on_abnormal: bool = True


def _tpl_dict(t: InspectionTemplate) -> dict:
    return {"id": t.id, "name": t.name, "device_type": t.device_type,
            "items": t.items or [], "active": bool(t.active)}


@router.get("/templates", summary="点检模板列表")
def list_templates(device_type: Optional[str] = None, db: Session = Depends(get_db)):
    q = db.query(InspectionTemplate).filter(InspectionTemplate.active.is_(True))
    if device_type:
        q = q.filter(InspectionTemplate.device_type == device_type)
    return {"items": [_tpl_dict(t) for t in q.order_by(InspectionTemplate.id).all()]}


@router.post("/templates", summary="新建点检模板（主管/管理员）")
def create_template(data: TemplateIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_supervisor)):
    t = InspectionTemplate(
        name=data.name, device_type=data.device_type,
        items=[i.model_dump() for i in data.items], active=data.active,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _tpl_dict(t)


@router.put("/templates/{tpl_id}", summary="修改点检模板（主管/管理员）")
def update_template(tpl_id: int, data: TemplateIn, db: Session = Depends(get_db),
                    current_user: User = Depends(require_supervisor)):
    t = db.query(InspectionTemplate).filter(InspectionTemplate.id == tpl_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="模板不存在")
    t.name, t.device_type = data.name, data.device_type
    t.items = [i.model_dump() for i in data.items]
    t.active = data.active
    db.commit()
    db.refresh(t)
    return _tpl_dict(t)


@router.delete("/templates/{tpl_id}", summary="删除点检模板（主管/管理员）")
def delete_template(tpl_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(require_supervisor)):
    t = db.query(InspectionTemplate).filter(InspectionTemplate.id == tpl_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="模板不存在")
    db.delete(t)
    db.commit()
    return {"message": "已删除"}


@router.post("/records", summary="提交点检记录（异常可自动建单）")
def create_record(data: RecordIn, db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    tpl = db.query(InspectionTemplate).filter(InspectionTemplate.id == data.template_id).first()
    if not tpl:
        raise HTTPException(status_code=404, detail="点检模板不存在")
    dev = db.query(Device).filter(Device.device_code == data.device_code).first()

    abnormal = [r for r in data.results if not r.ok]
    wo_id = None
    if abnormal and data.create_work_order_on_abnormal:
        desc = "；".join(
            f"{r.name}" + (f"（{r.value or ''}）" if r.value else "") + (f" - {r.remark}" if r.remark else "")
            for r in abnormal
        )
        wo = WorkOrder(
            work_order_no=f"INSP-{datetime.now():%Y%m%d%H%M%S}",
            device_id=dev.id if dev else None, device_code=data.device_code,
            fault_description=f"点检异常：{desc}"[:500],
            fault_category="点检异常", priority="HIGH",
            status=WorkOrderStatus.DRAFT,
            created_by=current_user.id, technician_id=current_user.id,
        )
        db.add(wo)
        db.flush()
        wo_id = wo.id

    rec = InspectionRecord(
        template_id=tpl.id, template_name=tpl.name,
        device_id=dev.id if dev else None, device_code=data.device_code,
        inspector_id=current_user.id, inspector_name=current_user.real_name,
        result="ABNORMAL" if abnormal else "OK",
        abnormal_count=len(abnormal),
        results=[r.model_dump() for r in data.results],
        remark=data.remark, work_order_id=wo_id,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    logger.info(f"[Inspection] {data.device_code} 点检 {len(data.results)} 项，异常 {len(abnormal)} 项")
    return {"message": "点检已提交", "id": rec.id, "result": rec.result,
            "abnormal_count": rec.abnormal_count, "work_order_id": wo_id}


@router.get("/records", summary="点检记录")
def list_records(
    device_code: Optional[str] = None,
    result: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = db.query(InspectionRecord)
    if device_code:
        q = q.filter(InspectionRecord.device_code == device_code)
    if result:
        q = q.filter(InspectionRecord.result == result.upper())
    total = q.count()
    rows = q.order_by(InspectionRecord.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"total": total, "page": page, "page_size": page_size, "items": [{
        "id": r.id, "template_name": r.template_name, "device_code": r.device_code,
        "inspector_name": r.inspector_name, "result": r.result,
        "abnormal_count": r.abnormal_count, "results": r.results,
        "remark": r.remark, "work_order_id": r.work_order_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    } for r in rows]}

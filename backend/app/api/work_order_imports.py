"""历史工单 PDF 导入 API

流程：
1. 上传 PDF 文件 → 保存到 uploads/pdf_import → 建批次 → 逐份跑 LangGraph 导入流水线
   （解析→DeepSeek 结构化抽取→校验→保存为待确认记录 WorkOrderImportItem）
2. 后台人工核对/修改/确认
3. 确认后才写入 work_orders 并收录知识库（去重到知识库在人工确认之后）
"""
import os
import re
import json
import uuid
from datetime import date, datetime, time
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Form
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from loguru import logger

from app.core.database import get_db, SessionLocal
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.models.work_order_import import WorkOrderImportBatch, WorkOrderImportItem
from app.models.work_order import WorkOrder
from app.models.device import Device
from app.agents.work_order_importer import invoke_import_pdf
from app.services.import_validate import validate_extracted
from app.services.excel_import import (
    FIELD_DEFS, build_template_xlsx, read_table, suggest_mapping,
    resolve_mapping, parse_sheet,
)
from app.services.image_ocr import ocr_image, structure_text

router = APIRouter(tags=["历史工单导入"])

IMPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads", "pdf_import",
)

# 历史工单由维修员（TECHNICIAN）负责核对确认，管理员/主管保留权限
_MANAGE_ROLES = {UserRole.ADMIN.value, UserRole.SUPERVISOR.value, UserRole.TECHNICIAN.value, "MANAGER"}



def _norm_service_mode(v):
    """服务方式归一：远程/现场/返厂/REMOTE/SITE/RMA -> 枚举值"""
    if v is None:
        return None
    t = str(v).strip().upper()
    if not t:
        return None
    if t in ("REMOTE", "远程", "远程处理", "远程支持"):
        return "REMOTE"
    if t in ("SITE", "现场", "现场处理", "上门"):
        return "SITE"
    if t in ("RMA", "返厂", "返厂维修", "返修", "送修"):
        return "RMA"
    return None


def _norm_bool(v):
    """是否返厂归一"""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    t = str(v).strip().lower()
    if t in ("1", "true", "yes", "y", "是", "需要", "需返厂", "返厂"):
        return True
    if t in ("0", "false", "no", "n", "否", "不需要", "无需"):
        return False
    return None


def _require_manage(current_user: User):
    if current_user.role not in _MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="仅管理员/主管/维修员可执行历史工单导入")


# ============================================================
# 上传并跑 LangGraph 流水线
# ============================================================
class UploadResult(BaseModel):
    file_name: str
    status: str          # PENDING / ERROR
    item_id: Optional[int] = None
    message: str = ""


@router.post("/upload", summary="上传历史工单 PDF 并批量抽取（LangGraph 流水线）")
async def upload_pdf_workorders(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manage(current_user)
    if not files:
        raise HTTPException(status_code=400, detail="请选择 PDF 文件")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="单次最多上传 50 份 PDF")

    os.makedirs(IMPORT_DIR, exist_ok=True)

    # 1. 建批次
    batch = WorkOrderImportBatch(
        batch_no=f"IMPORT-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}",
        source="PDF",
        status="PROCESSING",
        file_count=len(files),
        created_by=current_user.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    results: List[dict] = []
    saved_paths = []
    try:
        # 2. 保存文件并逐份跑流水线
        for f in files:
            ext = os.path.splitext(f.filename or "")[1].lower()
            if ext != ".pdf":
                results.append({"file_name": f.filename or "", "status": "ERROR",
                                "message": f"不支持的文件类型: {ext or '未知'}"})
                continue
            unique_name = f"{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}.pdf"
            file_path = os.path.join(IMPORT_DIR, unique_name)
            content = await f.read()
            with open(file_path, "wb") as fp:
                fp.write(content)
            saved_paths.append(file_path)

            try:
                r = invoke_import_pdf(file_path, f.filename or unique_name, batch.id)
            except Exception as e:
                logger.exception(f"[WOImport] 处理异常: {f.filename}")
                r = {"file_name": f.filename or unique_name, "status": "ERROR",
                     "message": f"处理异常: {e}"}
            results.append(r)

        # 3. 汇总批次
        pending = sum(1 for r in results if r.get("status") == "PENDING")
        failed = sum(1 for r in results if r.get("status") == "ERROR")
        batch.total_count = pending
        batch.failed_count = failed
        batch.status = "DONE" if failed == 0 else "PARTIAL"
        batch.report = results
        db.commit()
    except Exception as e:
        logger.exception("[WOImport] 上传批次处理失败")
        batch.status = "PARTIAL"
        batch.report = results
        db.commit()
        raise HTTPException(status_code=500, detail=f"批量处理失败: {e}")

    return {
        "batch_id": batch.id,
        "batch_no": batch.batch_no,
        "status": batch.status,
        "total_pending": batch.total_count,
        "failed": batch.failed_count,
        "results": results,
    }


# ============================================================
# 批次 / 待确认清单
# ============================================================
@router.get("/batches", summary="导入批次列表")
def list_batches(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manage(current_user)
    total = db.query(WorkOrderImportBatch).count()
    items = (
        db.query(WorkOrderImportBatch)
        .order_by(WorkOrderImportBatch.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
        .all()
    )
    return {
        "total": total,
        "items": [{
            "id": b.id,
            "batch_no": b.batch_no,
            "source": b.source or "PDF",
            "status": b.status,
            "file_count": b.file_count,
            "total_count": b.total_count,
            "success_count": b.success_count,
            "failed_count": b.failed_count,
            "created_at": b.created_at,
            "report": b.report,
        } for b in items],
        "page": page,
        "page_size": page_size,
    }


@router.get("/items", summary="待确认/已处理清单")
def list_items(
    batch_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None, description="PENDING/CONFIRMED/REJECTED/ERROR"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manage(current_user)
    query = db.query(WorkOrderImportItem)
    if batch_id:
        query = query.filter(WorkOrderImportItem.batch_id == batch_id)
    if status:
        query = query.filter(WorkOrderImportItem.status == status)
    total = query.count()
    items = (
        query.order_by(WorkOrderImportItem.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
        .all()
    )
    return {
        "total": total,
        "items": [{
            "id": it.id,
            "batch_id": it.batch_id,
            "file_name": it.file_name,
            "row_no": it.row_no,
            "source": (it.batch.source if it.batch else None),
            "status": it.status,
            "error_message": it.error_message,
            "extracted_data": it.extracted_data,
            "validate_warnings": it.validate_warnings or [],
            "image_url": _file_url(it.file_path),
            "work_order_id": it.work_order_id,
            "created_at": it.created_at,
            "confirmed_at": it.confirmed_at,
        } for it in items],
        "page": page,
        "page_size": page_size,
    }


# ============================================================
# 人工编辑 / 确认 / 拒绝
# ============================================================
class ItemUpdate(BaseModel):
    extracted_data: dict


@router.put("/items/{item_id}", summary="人工修改抽取结果")
def update_item(
    item_id: int,
    data: ItemUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manage(current_user)
    item = db.query(WorkOrderImportItem).filter(WorkOrderImportItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="记录不存在")
    if item.status == "CONFIRMED":
        raise HTTPException(status_code=400, detail="已确认入库的记录不可再修改")
    item.extracted_data = data.extracted_data
    db.commit()
    return {"message": "已保存修改"}


def _parse_dt(value) -> Optional[datetime]:
    """解析 YYYY-MM-DD HH:MM / YYYY-MM-DD 字符串"""
    if not value:
        return None
    s = str(value).strip()
    try:
        if "T" in s:
            return datetime.fromisoformat(s)
        if re.match(r"\d{4}-\d{2}-\d{2}$", s):
            return datetime.combine(datetime.strptime(s, "%Y-%m-%d").date(), time.min)
        return datetime.strptime(s, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return None


def _gen_wo_no(db: Session) -> str:
    today_str = date.today().strftime("%Y%m%d")
    prefix = f"WO-{today_str}-"
    latest = (
        db.query(WorkOrder)
        .filter(WorkOrder.work_order_no.like(f"{prefix}%"))
        .order_by(WorkOrder.work_order_no.desc())
        .first()
    )
    seq = 1
    if latest and latest.work_order_no:
        try:
            seq = int(latest.work_order_no.split("-")[-1]) + 1
        except ValueError:
            seq = 1
    return f"{prefix}{seq:03d}"


def _resolve_user(db: Session, name: Optional[str]) -> Optional[int]:
    if not name:
        return None
    u = db.query(User).filter(User.real_name == str(name).strip()).first()
    return u.id if u else None


@router.post("/items/{item_id}/confirm", summary="确认入库（写入工单 + 收录知识库）")
def confirm_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manage(current_user)
    item = db.query(WorkOrderImportItem).filter(WorkOrderImportItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="记录不存在")
    if item.status == "CONFIRMED":
        return {"message": "该记录已确认入库", "work_order_id": item.work_order_id}
    data = item.extracted_data or {}

    # 工单号：已有则校验唯一，否则自动生成
    wo_no = str(data.get("work_order_no") or "").strip()
    if wo_no:
        if db.query(WorkOrder).filter(WorkOrder.work_order_no == wo_no).first():
            raise HTTPException(status_code=400, detail=f"工单号 {wo_no} 已存在，请修改后重试")
    else:
        wo_no = _gen_wo_no(db)

    fault_description = str(data.get("fault_description") or "").strip()
    if not fault_description:
        raise HTTPException(status_code=400, detail="故障描述不能为空")

    # 设备 / 用户
    device_id = data.get("device_id")
    if not device_id and data.get("device_code"):
        dev = db.query(Device).filter(Device.device_code == str(data["device_code"])).first()
        device_id = dev.id if dev else None
    technician_id = data.get("technician_id") or _resolve_user(db, data.get("technician_name"))
    reporter_id = data.get("reporter_id") or _resolve_user(db, data.get("reporter_name"))

    wo = WorkOrder(
        work_order_no=wo_no,
        device_id=device_id,
        device_code=str(data.get("device_code") or "") or None,
        fault_code=str(data.get("fault_code") or ""),
        fault_description=fault_description,
        fault_category=data.get("fault_category") or None,
        order_type="IMPORT",
        fault_phenomenon_type=data.get("fault_phenomenon_type") or None,
        fault_phenomenon=data.get("fault_phenomenon") or None,
        gpu_index=(str(data.get("gpu_index")).strip() or None) if data.get("gpu_index") else None,
        fault_device_sn=(str(data.get("fault_device_sn")).strip() or None) if data.get("fault_device_sn") else None,
        service_mode=_norm_service_mode(data.get("service_mode")),
        need_rma=_norm_bool(data.get("need_rma")),
        root_cause_category=data.get("root_cause_category") or None,
        root_cause=data.get("root_cause") or None,
        solution_steps=data.get("solution_steps") or None,
        repair_result=data.get("repair_result") or None,
        work_hours=float(data["work_hours"]) if data.get("work_hours") else None,
        used_parts=data.get("used_parts") or None,
        priority=data.get("priority") or "MEDIUM",
        location=data.get("location") or None,
        start_time=_parse_dt(data.get("start_time")),
        end_time=_parse_dt(data.get("end_time")),
        technician_id=technician_id,
        reporter_id=reporter_id,
        tags=data.get("tags") or None,
        status="ARCHIVED",  # 历史工单已完工，直接归档
        created_by=current_user.id,
    )
    # 拍照导入：把原始图片挂到工单附件，详情页可直接查看原图
    image_url = _file_url(item.file_path)
    if image_url:
        wo.attachments = [{
            "url": image_url,
            "name": item.file_name or os.path.basename(item.file_path),
            "type": "image",
        }]
    db.add(wo)
    db.flush()

    # 收录知识库（人工确认之后才去重收录）
    knowledge_synced = False
    try:
        from app.api.work_orders import _auto_publish_knowledge
        knowledge_synced = bool(_auto_publish_knowledge(wo, db))
    except Exception as e:
        logger.warning(f"[WOImport] 知识库收录失败: {e}")

    db.commit()
    db.refresh(wo)

    item.status = "CONFIRMED"
    item.work_order_id = wo.id
    item.confirmed_at = datetime.now()
    item.confirmed_by = current_user.id
    batch = db.query(WorkOrderImportBatch).filter(WorkOrderImportBatch.id == item.batch_id).first()
    if batch:
        batch.success_count = (batch.success_count or 0) + 1
    db.commit()

    logger.info(f"[WOImport] 确认入库: item={item.id} wo={wo_no} knowledge={knowledge_synced}")
    return {
        "message": "已确认入库并收录知识库" if knowledge_synced else "已确认入库（知识库跳过/提取失败）",
        "work_order_id": wo.id,
        "work_order_no": wo_no,
        "knowledge_synced": knowledge_synced,
    }


@router.post("/items/{item_id}/reject", summary="拒绝该条记录")
def reject_item(
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manage(current_user)
    item = db.query(WorkOrderImportItem).filter(WorkOrderImportItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="记录不存在")
    if item.status == "CONFIRMED":
        raise HTTPException(status_code=400, detail="已确认入库的记录不可拒绝")
    item.status = "REJECTED"
    db.commit()
    return {"message": "已拒绝该记录"}


# ============================================================
# Excel / CSV 台账导入
# ============================================================
EXCEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads", "excel_import",
)
IMAGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads", "image_import",
)

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/template", summary="下载 Excel 导入模板")
def download_template(current_user: User = Depends(get_current_user)):
    _require_manage(current_user)
    data = build_template_xlsx()
    from urllib.parse import quote
    filename = quote("工单导入模板.xlsx")
    return Response(
        content=data,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename=template.xlsx; filename*=UTF-8''{filename}"},
    )


@router.get("/fields", summary="可映射的系统字段清单")
def list_fields(current_user: User = Depends(get_current_user)):
    _require_manage(current_user)
    return {"fields": [{"key": f["key"], "label": f["label"], "required": f["required"]} for f in FIELD_DEFS]}


async def _save_upload(file: UploadFile, directory: str, allowed: set) -> str:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型：{ext or '未知'}")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, f"{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:12]}{ext}")
    with open(path, "wb") as fp:
        fp.write(await file.read())
    return path


@router.post("/excel/inspect", summary="预检 Excel 表头并给出字段映射建议")
async def inspect_excel(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
):
    _require_manage(current_user)
    path = await _save_upload(file, EXCEL_DIR, {".xlsx", ".xlsm", ".csv", ".xls"})
    try:
        headers, rows = read_table(path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    mapping = suggest_mapping(headers)
    preview = []
    for r in rows[:5]:
        preview.append({h: (r[i] if i < len(r) else "") for i, h in enumerate(headers)})
    return {
        "file_name": file.filename,
        "headers": headers,
        "mapping": mapping,
        "row_count": len(rows),
        "preview": preview,
        "fields": [{"key": f["key"], "label": f["label"], "required": f["required"]} for f in FIELD_DEFS],
    }


@router.post("/upload-excel", summary="导入 Excel/CSV 台账（逐行校验，生成待确认记录）")
async def upload_excel(
    file: UploadFile = File(...),
    mapping: Optional[str] = Form(None, description="JSON 字符串：{系统字段: 表格列名}，不传则自动匹配"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manage(current_user)
    path = await _save_upload(file, EXCEL_DIR, {".xlsx", ".xlsm", ".csv", ".xls"})
    try:
        headers, rows = read_table(path)
    except Exception as e:
        logger.warning(f"[ExcelImport] 解析失败 {file.filename}: {e}")
        raise HTTPException(
            status_code=400,
            detail="无法解析该文件：请确认是有效的 Excel(.xlsx/.xlsm) 或 CSV 文件（另存为 .xlsx 再试）",
        )

    user_mapping = None
    if mapping:
        try:
            user_mapping = json.loads(mapping)
        except Exception:
            raise HTTPException(status_code=400, detail="字段映射格式错误（需为 JSON）")
    col_index = resolve_mapping(headers, user_mapping or suggest_mapping(headers))
    if not any(k in col_index for k in ("fault_description", "fault_phenomenon", "root_cause")):
        raise HTTPException(
            status_code=400,
            detail="未映射「故障描述」列，也没有「故障现象」或「根本原因」列可兜底，无法导入",
        )

    # 只有表头没有数据行时不要建空批次（原来会留下 0 条的空记录）
    if not rows:
        raise HTTPException(status_code=400, detail="表格里没有数据行（只有表头），没有可导入的内容")

    batch = WorkOrderImportBatch(
        batch_no=f"EXCEL-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}",
        source="EXCEL",
        status="PROCESSING",
        file_count=1,
        created_by=current_user.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    parsed = parse_sheet(headers, rows, col_index)
    seen_numbers: set = set()
    seen_nos_in_file: set = set()
    results: List[dict] = []
    ok_count = 0

    for row in parsed:
        row_no = row["row_no"]
        label = f"{file.filename} 第{row_no}行"
        if row["errors"]:
            item = WorkOrderImportItem(
                batch_id=batch.id, file_name=label, file_path=path, row_no=row_no,
                status="ERROR", error_message="；".join(row["errors"]),
                extracted_data={"_raw_row": dict(zip(headers, row["raw"]))},
            )
            db.add(item)
            results.append({"row_no": row_no, "status": "ERROR", "message": "；".join(row["errors"])})
            continue

        data, warnings = validate_extracted(db, row["data"], seen_numbers)
        warnings = list(row["warnings"]) + warnings

        # 工单号冲突（文件内重复 / 系统内已存在）直接标 ERROR，
        # 否则用户逐条点"确认入库"时才撞唯一约束，白点一遍
        wo_no = str(data.get("work_order_no") or "").strip()
        dup_msg = ""
        if wo_no:
            if wo_no in seen_nos_in_file:
                dup_msg = f"工单号 {wo_no} 在本文件内重复"
            elif db.query(WorkOrder).filter(WorkOrder.work_order_no == wo_no).first():
                dup_msg = f"工单号 {wo_no} 已存在于系统"
            else:
                seen_nos_in_file.add(wo_no)
        if dup_msg:
            db.add(WorkOrderImportItem(
                batch_id=batch.id, file_name=label, file_path=path, row_no=row_no,
                status="ERROR", error_message=dup_msg,
                extracted_data={"_raw_row": dict(zip(headers, row["raw"]))},
            ))
            results.append({"row_no": row_no, "status": "ERROR", "message": dup_msg})
            continue

        item = WorkOrderImportItem(
            batch_id=batch.id, file_name=label, file_path=path, row_no=row_no,
            status="PENDING",
            extracted_text="；".join(f"{headers[i]}={row['raw'][i]}" for i in range(min(len(headers), len(row["raw"]))) if row["raw"][i])[:4000],
            extracted_data=data,
            validate_warnings=warnings,
        )
        db.add(item)
        ok_count += 1
        results.append({
            "row_no": row_no, "status": "PENDING",
            "work_order_no": data.get("work_order_no") or "",
            "fault_description": data.get("fault_description") or "",
            "message": f"{len(warnings)} 项提示" if warnings else "校验通过",
        })

    total = len(parsed)
    batch.total_count = ok_count
    batch.failed_count = total - ok_count
    batch.file_count = 1
    batch.status = "DONE" if batch.failed_count == 0 else "PARTIAL"
    batch.report = {"file": file.filename, "headers": headers, "mapping": col_index, "rows": results}
    db.commit()

    return {
        "batch_id": batch.id,
        "batch_no": batch.batch_no,
        "source": "EXCEL",
        "total_rows": total,
        "pending": ok_count,
        "failed": batch.failed_count,
        "mapping": {k: headers[v] for k, v in col_index.items() if v < len(headers)},
        "results": results,
    }


# ============================================================
# 图片（纸质工单拍照）OCR 导入
# ============================================================
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def _file_url(path: Optional[str]) -> Optional[str]:
    """把服务器端保存的文件路径转换为静态访问 URL（仅图片）"""
    if not path:
        return None
    if os.path.splitext(path)[1].lower() in _IMAGE_EXTS:
        return f"/api/v1/upload/files/image_import/{os.path.basename(path)}"
    return None


@router.post("/upload-images", summary="导入纸质工单照片/扫描件（本地 OCR 识别）")
async def upload_images(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_manage(current_user)
    if not files:
        raise HTTPException(status_code=400, detail="请选择图片文件")
    if len(files) > 30:
        raise HTTPException(status_code=400, detail="单次最多上传 30 张图片")

    batch = WorkOrderImportBatch(
        batch_no=f"IMAGE-{datetime.now().strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:4]}",
        source="IMAGE",
        status="PROCESSING",
        file_count=len(files),
        created_by=current_user.id,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    results: List[dict] = []
    ok_count = 0
    failed = 0
    seen_numbers: set = set()

    for f in files:
        ext = os.path.splitext(f.filename or "")[1].lower()
        if ext not in _IMAGE_EXTS:
            results.append({"file_name": f.filename or "", "status": "ERROR",
                            "message": f"不支持的图片格式：{ext or '未知'}"})
            failed += 1
            continue
        path = await _save_upload(f, IMAGE_DIR, _IMAGE_EXTS)
        try:
            text = ocr_image(path)
        except Exception as e:
            logger.exception(f"[ImageImport] OCR 失败: {f.filename}")
            text = ""
            err = f"OCR 识别失败：{e}"
        else:
            err = "" if text else "未识别到文字，请检查图片清晰度或裁掉无关区域"

        if err:
            db.add(WorkOrderImportItem(
                batch_id=batch.id, file_name=f.filename or "", file_path=path,
                status="ERROR", error_message=err,
            ))
            results.append({"file_name": f.filename or "", "status": "ERROR", "message": err})
            failed += 1
            continue

        data, warnings = structure_text(text)
        data, extra = validate_extracted(db, data, seen_numbers)
        warnings = warnings + extra
        item = WorkOrderImportItem(
            batch_id=batch.id, file_name=f.filename or "", file_path=path,
            status="PENDING", extracted_text=text[:4000],
            extracted_data=data, validate_warnings=warnings,
        )
        db.add(item)
        db.flush()
        ok_count += 1
        results.append({
            "file_name": f.filename or "", "status": "PENDING", "item_id": item.id,
            "work_order_no": data.get("work_order_no") or "",
            "message": f"识别 {len(text)} 字，{len(warnings)} 项提示",
        })

    batch.total_count = ok_count
    batch.failed_count = failed
    batch.status = "DONE" if failed == 0 else "PARTIAL"
    batch.report = results
    db.commit()

    return {
        "batch_id": batch.id, "batch_no": batch.batch_no, "source": "IMAGE",
        "pending": ok_count, "failed": failed, "results": results,
    }

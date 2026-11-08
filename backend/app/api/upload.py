"""文件上传 API - 本地存储

安全要点（2026-11-08 加固）：
1. 必须登录（router 级鉴权）
2. 单文件大小上限 MAX_UPLOAD_MB（默认 20MB），超限即中断并删除临时文件
3. 校验文件头（magic number），不能只信扩展名
4. 分块写盘，避免大文件一次性读进内存
"""
import os
import uuid
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from loguru import logger

from app.core.config import settings
from app.core.security import get_current_user

router = APIRouter(prefix="/upload", tags=["文件上传"],
                   dependencies=[Depends(get_current_user)])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "uploads")

# 扩展名 -> 允许的文件头特征
_MAGIC = {
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".gif": [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"],
    ".mp4": [b"ftyp"],
    ".mov": [b"ftyp"],
    ".webm": [b"\x1a\x45\xdf\xa3"],
    ".avi": [b"RIFF"],
}
ALLOWED_EXTENSIONS = set(_MAGIC.keys())
CHUNK = 1024 * 1024


def _sniff_ok(head: bytes, ext: str) -> bool:
    """按扩展名对应的特征做简单文件头校验"""
    sigs = _MAGIC.get(ext, [])
    if not sigs:
        return False
    if ext in (".mp4", ".mov"):
        return len(head) >= 12 and head[4:8] == b"ftyp"
    if ext in (".webp", ".avi"):
        return head[:4] == b"RIFF"
    return any(head.startswith(s) for s in sigs)


@router.post("/work-order-image", summary="上传工单附件图片/视频")
async def upload_work_order_image(file: UploadFile = File(...)):
    """上传图片或视频，返回文件 URL（限 20MB，校验文件头）"""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"不支持的文件类型: {ext or '未知'}")

    max_bytes = int(getattr(settings, "MAX_UPLOAD_MB", 20)) * 1024 * 1024

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d")
    unique_name = f"{date_str}_{uuid.uuid4().hex[:12]}{ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_name)

    size = 0
    head = b""
    try:
        with open(file_path, "wb") as f:
            while True:
                chunk = await file.read(CHUNK)
                if not chunk:
                    break
                if not head:
                    head = chunk[:16]
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过上限 {getattr(settings, 'MAX_UPLOAD_MB', 20)}MB",
                    )
                f.write(chunk)
    except HTTPException:
        if os.path.exists(file_path):
            os.remove(file_path)
        raise
    except Exception as e:
        if os.path.exists(file_path):
            os.remove(file_path)
        logger.error(f"[Upload] 写盘失败: {e}")
        raise HTTPException(status_code=500, detail="文件保存失败")

    if size == 0:
        os.remove(file_path)
        raise HTTPException(status_code=400, detail="文件内容为空")
    if not _sniff_ok(head, ext):
        os.remove(file_path)
        raise HTTPException(status_code=400, detail=f"文件内容与扩展名 {ext} 不匹配")

    url = f"/api/v1/upload/files/{unique_name}"
    logger.info(f"[Upload] 文件上传成功: {unique_name} ({size} bytes)")
    return {
        "url": url,
        "name": file.filename,
        "size": size,
        "type": "video" if ext in {".mp4", ".mov", ".avi", ".webm"} else "image",
    }

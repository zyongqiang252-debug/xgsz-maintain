"""系统设置 API：管理员在网页上接入第三方服务（DeepSeek / 钉钉群机器人）

设计要点：
- 只允许 ADMIN
- 密钥**只写不读**：查询接口一律打码返回
- 保存在数据库 `sys_configs`，保存后热生效（自动重置 Agent 缓存的 LLM 客户端），重启也自动加载
- 提供「测试连接」，避免配错了要到业务里才发现
"""
import time
from typing import Optional

import requests
from fastapi import APIRouter, Depends, HTTPException
from loguru import logger
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import runtime_settings as rt
from app.core.config import settings
from app.core.database import get_db
from app.core.dingtalk_group import group_robot
from app.core.security import require_admin
from app.models.user import User

router = APIRouter(tags=["系统设置"], dependencies=[Depends(require_admin)])


class AISettingsIn(BaseModel):
    # 三个字段都可选：只传要改的；api_key 传空串表示清除
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    allow_general: Optional[bool] = None


class GroupRobotIn(BaseModel):
    webhook: Optional[str] = None
    secret: Optional[str] = None


def _ai_status() -> dict:
    key = settings.DEEPSEEK_API_KEY or ""
    return {
        "configured": bool(key),
        "api_key_masked": rt.mask_secret(key),
        "base_url": settings.DEEPSEEK_BASE_URL,
        "model": settings.DEEPSEEK_MODEL,
        "allow_general": bool(settings.AI_ALLOW_GENERAL_ANSWER),
        "callable": bool(key),
    }


@router.get("/overview", summary="各第三方接入状态总览")
def overview():
    return {
        "deepseek": _ai_status(),
        "sms": {
            "enabled": bool(settings.SMS_ENABLED),
            "configured": bool(settings.SMS_ACCESS_KEY_ID and settings.SMS_ACCESS_KEY_SECRET),
            "sign_name": settings.SMS_SIGN_NAME or "",
        },
        "dingtalk": {
            "mock_mode": bool(settings.DINGTALK_MOCK_MODE),
            "app_key_configured": bool(settings.DINGTALK_APP_KEY),
            "redirect_uri": settings.DINGTALK_REDIRECT_URI,
        },
        "group_robot": {
            "enabled": group_robot.enabled,
            "webhook_masked": group_robot.masked_webhook(),
            "signed": bool(group_robot.secret),
        },
        "milvus": {
            "host": settings.MILVUS_HOST,
            "port": settings.MILVUS_PORT,
            "note": "未部署时检索自动降级为 BM25",
        },
    }


@router.get("/ai", summary="读取 AI 接入配置（密钥打码）")
def get_ai_settings():
    return _ai_status()


@router.put("/ai", summary="保存 AI 接入配置（保存即生效）")
def save_ai_settings(data: AISettingsIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_admin)):
    if data.api_key is not None and data.api_key.strip() and len(data.api_key.strip()) < 10:
        raise HTTPException(status_code=400, detail="API Key 格式不对（长度不足）")
    changed = rt.save_ai(db, api_key=data.api_key, base_url=data.base_url,
                        model=data.model, allow_general=data.allow_general)
    logger.info(f"[SystemSettings] {current_user.real_name} 更新 AI 配置: {list(changed.keys())}")
    return {"message": "已保存并生效", "current": _ai_status(),
            "changed": [k for k in changed]}


class AITestIn(BaseModel):
    """测试连接：可传当前表单里的值，未保存也能先试"""
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None


@router.post("/ai/test", summary="测试 AI 连通性（可用表单里未保存的值）")
def test_ai(body: Optional[AITestIn] = None, current_user: User = Depends(require_admin)):
    key = ((body.api_key if body else None) or settings.DEEPSEEK_API_KEY or "").strip()
    base_url = ((body.base_url if body else None) or settings.DEEPSEEK_BASE_URL or "").strip()
    model = ((body.model if body else None) or settings.DEEPSEEK_MODEL or "").strip()
    if not key:
        raise HTTPException(
            status_code=400,
            detail="还没填 API Key：把 sk- 开头的密钥贴到上面的输入框，再点「测试连接」或「保存并生效」",
        )
    url = base_url.rstrip("/") + "/chat/completions"
    req_body = {
        "model": model,
        "messages": [{"role": "user", "content": "回复两个字：收到"}],
        "max_tokens": 16,
        "stream": False,
    }
    t0 = time.time()
    try:
        resp = requests.post(url, json=req_body, timeout=20,
                             headers={"Authorization": f"Bearer {key}",
                                      "Content-Type": "application/json"})
        cost = int((time.time() - t0) * 1000)
        if resp.status_code != 200:
            raise HTTPException(status_code=400,
                                detail=f"接口返回 {resp.status_code}：{resp.text[:200]}")
        resp_json = resp.json()
        reply = (resp_json.get("choices") or [{}])[0].get("message", {}).get("content", "")
        usage = resp_json.get("usage") or {}
        return {
            "ok": True,
            "latency_ms": cost,
            "model": resp_json.get("model") or model,
            "reply": (reply or "").strip()[:50],
            "tokens": usage.get("total_tokens"),
            "tested_unsaved": bool(body and body.api_key),
        }
    except HTTPException:
        raise
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=400, detail=f"连接失败：{e}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"调用异常：{e}")


@router.get("/dingtalk-group", summary="读取群机器人配置（密钥打码）")
def get_group_robot():
    return {
        "enabled": group_robot.enabled,
        "webhook_masked": group_robot.masked_webhook(),
        "signed": bool(group_robot.secret),
    }


@router.put("/dingtalk-group", summary="保存群机器人配置（保存即生效）")
def save_group_robot(data: GroupRobotIn, db: Session = Depends(get_db),
                     current_user: User = Depends(require_admin)):
    if data.webhook is not None and data.webhook.strip() and "access_token" not in data.webhook:
        raise HTTPException(status_code=400, detail="Webhook 不像钉钉机器人地址（应含 access_token=）")
    rt.save_group_robot(db, webhook=data.webhook, secret=data.secret)
    logger.info(f"[SystemSettings] {current_user.real_name} 更新群机器人配置")
    return {"message": "已保存并生效", "current": get_group_robot()}


@router.post("/dingtalk-group/test", summary="往群里发一条测试消息")
def test_group_robot(current_user: User = Depends(require_admin)):
    if not group_robot.enabled:
        raise HTTPException(status_code=400, detail="还没配置群机器人 Webhook")
    res = group_robot.send_markdown(
        "芯光数智 · 测试消息",
        f"### ✅ 群机器人连通测试\n\n- 操作人：{current_user.real_name}\n\n"
        f"收到这条说明配置成功。",
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=f"发送失败：{res.get('resp') or res.get('error')}")
    return {"ok": True, "resp": res.get("resp")}

"""运行时配置：把数据库里存的第三方接入参数应用到 settings，并支持热更新

为什么需要：
- 原来 DeepSeek Key / 群机器人 webhook 只能写死在 backend/.env，改一次要重启
- 现在允许管理员在网页「系统设置」里填，存 `sys_configs` 表，保存即生效、重启后自动加载

安全：
- API Key / 群机器人 Webhook / 加签密钥 **加密后入库**（Fernet，见 app/core/crypto.py）
- 历史明文值在读取时自动就地加密（平滑迁移）
- 对外接口一律只返回打码值

优先级：**数据库 > .env > 代码默认值**（数据库没值时不动 settings）
"""
from typing import Dict, Optional

from loguru import logger
from sqlalchemy.orm import Session

from app.core import crypto, sys_config
from app.core.config import settings

# ---------- 配置键 ----------
KEY_API_KEY = "ai.deepseek_api_key"        # 敏感：加密存储
KEY_BASE_URL = "ai.deepseek_base_url"
KEY_MODEL = "ai.deepseek_model"
KEY_ALLOW_GENERAL = "ai.allow_general_answer"
KEY_GROUP_WEBHOOK = "dingtalk.group_webhook"   # 敏感：含 access_token，加密存储
KEY_GROUP_SECRET = "dingtalk.group_secret"     # 敏感：加密存储

SECRET_KEYS = {KEY_API_KEY, KEY_GROUP_WEBHOOK, KEY_GROUP_SECRET}

DESCRIPTIONS = {
    KEY_API_KEY: "DeepSeek API Key（加密存储；网页设置优先于 .env）",
    KEY_BASE_URL: "DeepSeek API Base URL",
    KEY_MODEL: "DeepSeek 模型名",
    KEY_ALLOW_GENERAL: "无相关案例时是否允许通用知识回答（标注非本厂案例）",
    KEY_GROUP_WEBHOOK: "钉钉群机器人 Webhook（加密存储）",
    KEY_GROUP_SECRET: "钉钉群机器人加签密钥（加密存储）",
}


def mask_secret(value: str) -> str:
    """密钥打码：sk-ab****yz"""
    v = (value or "").strip()
    if not v:
        return ""
    if len(v) <= 8:
        return "****"
    return f"{v[:4]}****{v[-4:]}"


def reset_ai_clients() -> int:
    """清掉各 Agent 里缓存的 LLM 客户端，让新配置立刻生效"""
    import importlib
    import pkgutil

    import app.agents as agents_pkg

    cleared = 0
    for m in pkgutil.iter_modules(agents_pkg.__path__):
        try:
            mod = importlib.import_module(f"app.agents.{m.name}")
        except Exception:
            continue
        for attr in dir(mod):
            if attr.startswith("__"):
                continue
            try:
                obj = getattr(mod, attr)
            except Exception:
                continue
            if hasattr(obj, "_llm"):
                try:
                    obj._llm = None
                    cleared += 1
                except Exception:
                    pass
    if cleared:
        logger.info(f"[RuntimeSettings] 已重置 {cleared} 个 Agent 的 LLM 客户端")
    return cleared


def apply_to_settings(values: Dict[str, Optional[str]]) -> None:
    """把 {配置键: 明文值} 应用到 settings（None 表示不动）"""
    if values.get(KEY_API_KEY) is not None:
        settings.DEEPSEEK_API_KEY = values[KEY_API_KEY] or ""
    if values.get(KEY_BASE_URL) is not None:
        settings.DEEPSEEK_BASE_URL = (values[KEY_BASE_URL] or "").strip() or "https://api.deepseek.com"
    if values.get(KEY_MODEL) is not None:
        settings.DEEPSEEK_MODEL = (values[KEY_MODEL] or "").strip() or "deepseek-chat"
    if values.get(KEY_ALLOW_GENERAL) is not None:
        v = values[KEY_ALLOW_GENERAL]
        settings.AI_ALLOW_GENERAL_ANSWER = str(v).strip().lower() in ("1", "true", "yes", "on")
    if values.get(KEY_GROUP_WEBHOOK) is not None:
        settings.DINGTALK_GROUP_WEBHOOK = (values[KEY_GROUP_WEBHOOK] or "").strip()
    if values.get(KEY_GROUP_SECRET) is not None:
        settings.DINGTALK_GROUP_SECRET = (values[KEY_GROUP_SECRET] or "").strip()
    reset_ai_clients()


def _read_value(db: Session, key: str, migrate: bool = True) -> Optional[str]:
    """读一条配置并解密；历史明文顺带就地加密"""
    raw = sys_config.get(db, key, None)
    if raw is None:
        return None
    if key in SECRET_KEYS:
        if not crypto.is_encrypted(raw) and raw:
            if migrate:
                try:
                    sys_config.set_value(db, key, crypto.encrypt(str(raw)), DESCRIPTIONS.get(key))
                    logger.info(f"[RuntimeSettings] 已把历史明文配置 {key} 迁移为密文")
                except Exception as e:
                    logger.warning(f"[RuntimeSettings] {key} 明文迁移失败: {e}")
            return str(raw)
        return crypto.decrypt(str(raw))
    return str(raw)


def load_into_settings(db: Session) -> int:
    """启动时把数据库里的配置加载进 settings，返回加载条数"""
    values = {}
    for key in DESCRIPTIONS:
        v = _read_value(db, key)
        if v is not None:
            values[key] = v
    if not values:
        logger.info("[RuntimeSettings] 数据库暂无第三方接入配置，沿用 .env")
        return 0
    apply_to_settings(values)
    logger.info(
        f"[RuntimeSettings] 已从数据库加载 {len(values)} 项接入配置"
        f"（DeepSeek Key：{'已配置' if settings.DEEPSEEK_API_KEY else '未配置'}，"
        f"群机器人：{'已配置' if settings.DINGTALK_GROUP_WEBHOOK else '未配置'}）"
    )
    return len(values)


def _write_value(db: Session, key: str, plain: str) -> None:
    """写一条配置（敏感项加密后落库）"""
    stored = crypto.encrypt(plain) if key in SECRET_KEYS else plain
    sys_config.set_value(db, key, stored, DESCRIPTIONS.get(key))


def save_ai(db: Session, api_key: Optional[str] = None,
            base_url: Optional[str] = None, model: Optional[str] = None,
            allow_general: Optional[bool] = None) -> Dict:
    """保存 AI 配置（传 None 表示不修改；传空串表示清空）"""
    changed = {}
    if api_key is not None:
        _write_value(db, KEY_API_KEY, api_key.strip())
        changed[KEY_API_KEY] = api_key.strip()
    if base_url is not None:
        _write_value(db, KEY_BASE_URL, base_url.strip())
        changed[KEY_BASE_URL] = base_url.strip()
    if model is not None:
        _write_value(db, KEY_MODEL, model.strip())
        changed[KEY_MODEL] = model.strip()
    if allow_general is not None:
        _write_value(db, KEY_ALLOW_GENERAL, "true" if allow_general else "false")
        changed[KEY_ALLOW_GENERAL] = "true" if allow_general else "false"
    apply_to_settings(changed)
    return changed


def save_group_robot(db: Session, webhook: Optional[str] = None,
                     secret: Optional[str] = None) -> Dict:
    changed = {}
    if webhook is not None:
        _write_value(db, KEY_GROUP_WEBHOOK, webhook.strip())
        changed[KEY_GROUP_WEBHOOK] = webhook.strip()
    if secret is not None:
        _write_value(db, KEY_GROUP_SECRET, secret.strip())
        changed[KEY_GROUP_SECRET] = secret.strip()
    apply_to_settings(changed)
    return changed

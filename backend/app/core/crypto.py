"""敏感配置的加解密（Fernet 对称加密）

用途：数据库里存的第三方 API Key（DeepSeek 等）加密后再落库，
即使有人拿到数据库备份/直连查询，也只能看到密文。

密钥来源（按优先级）：
1. `.env` 里的 `SETTINGS_ENC_KEY`（推荐：`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`）
2. 未配置时，用 `SECRET_KEY` 派生（不新增配置，但换 SECRET_KEY 会导致旧密文解不开）

密文格式：`enc:v1:<fernet_token>`；不带前缀的视为历史明文，读取时自动兼容并就地加密。
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from loguru import logger

from app.core.config import settings

PREFIX = "enc:v1:"


def _fernet() -> Fernet:
    raw = (getattr(settings, "SETTINGS_ENC_KEY", "") or "").strip()
    if raw:
        try:
            return Fernet(raw.encode())
        except Exception as e:
            logger.warning(f"[Crypto] SETTINGS_ENC_KEY 格式不对（需 Fernet 32 字节 base64）：{e}，回退到 SECRET_KEY 派生")
    seed = (settings.SECRET_KEY or "xgsz-maintain-fallback").encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(b"xgsz-settings:" + seed).digest())
    return Fernet(key)


def is_encrypted(value: str) -> bool:
    return bool(value) and str(value).startswith(PREFIX)


def encrypt(plain: str) -> str:
    """明文 → enc:v1:xxx；空值原样返回"""
    if plain is None or plain == "":
        return ""
    if is_encrypted(plain):
        return plain
    token = _fernet().encrypt(str(plain).encode("utf-8")).decode("ascii")
    return PREFIX + token


def decrypt(value: str) -> str:
    """enc:v1:xxx → 明文；历史明文原样返回；解密失败返回空串并告警"""
    if not value:
        return ""
    if not is_encrypted(value):
        return str(value)  # 兼容改造前的明文
    try:
        return _fernet().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken:
        logger.error("[Crypto] 配置解密失败：SETTINGS_ENC_KEY/SECRET_KEY 可能已更换，请重新录入 API Key")
        return ""
    except Exception as e:
        logger.error(f"[Crypto] 配置解密异常: {e}")
        return ""

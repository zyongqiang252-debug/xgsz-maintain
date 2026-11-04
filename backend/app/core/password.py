"""密码哈希工具

直接使用 bcrypt，绕开 passlib 1.7.4 与 bcrypt>=4.1 的不兼容问题
（passlib 已停止维护，其内部后端探测在新版 bcrypt 上会抛
"password cannot be longer than 72 bytes"，导致创建用户/注册/改密全部失败）。

bcrypt 只处理前 72 字节，超长密码统一截断，避免直接报错。
"""
import bcrypt

_MAX_BYTES = 72


def _prepare(password: str) -> bytes:
    if password is None:
        password = ""
    return str(password).encode("utf-8")[:_MAX_BYTES]


def hash_password(password: str) -> str:
    """生成 bcrypt 哈希（$2b$ 前缀）"""
    return bcrypt.hashpw(_prepare(password), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """校验 bcrypt 哈希；非 bcrypt 哈希或异常一律返回 False"""
    if not hashed or not str(hashed).startswith("$2"):
        return False
    try:
        return bcrypt.checkpw(_prepare(password), str(hashed).encode("utf-8"))
    except Exception:
        return False

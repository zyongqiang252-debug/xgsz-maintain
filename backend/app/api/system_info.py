"""系统网络信息：给「设备二维码 / 手机扫码报修」生成手机能访问的地址

手机扫 127.0.0.1 是打不开的（指向手机自己），
这里探测本机局域网 IP 并拼出建议的访问地址。
"""
import socket
from typing import List

from fastapi import APIRouter, Depends
from loguru import logger

from app.core.config import settings
from app.core.security import get_current_user

router = APIRouter(tags=["系统信息"], dependencies=[Depends(get_current_user)])


def _lan_ips() -> List[str]:
    """尽量列出本机可被局域网访问的 IPv4 地址"""
    ips: List[str] = []
    # 1) UDP 连接探路（不会真的发包），拿到默认出口网卡地址
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    # 2) 主机名解析出的所有地址
    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            ips.append(ip)
    except Exception:
        pass
    # 去重、过滤回环与 169.254 链路本地
    out = []
    for ip in ips:
        if ip.startswith("127.") or ip.startswith("169.254."):
            continue
        if ip not in out:
            out.append(ip)
    return out


@router.get("/network", summary="本机网络信息（用于生成手机可访问的二维码地址）")
def network_info():
    ips = _lan_ips()
    public = (getattr(settings, "SERVER_PUBLIC_URL", "") or "").rstrip("/")
    host = socket.gethostname()
    port = int(getattr(settings, "BACKEND_PORT", 18080) or 18080)

    if public:
        base = public
        source = "public_url"
    elif ips:
        base = f"http://{ips[0]}:{port}"
        source = "lan_ip"
    else:
        base = ""
        source = "none"

    return {
        "hostname": host,
        "port": port,
        "lan_ips": ips,
        "public_base_url": public,
        "suggested_base_url": base,
        "source": source,
        "hint": "手机需与电脑连接同一局域网（Wi-Fi）" if not public else "使用配置的公网地址",
    }

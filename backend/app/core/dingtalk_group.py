"""钉钉自定义群机器人主动推送（webhook + 加签）

和 `dingtalk.py` 里的"企业内部应用机器人"不是一回事：
- 企业内部机器人：要在应用里加机器人、走 Stream/回调，主要用于「接收指令 + 单聊回复」
- 自定义群机器人：只要一个 webhook 地址，往群里发消息，**不需要公网、不需要审批**

典型用途：新工单、派工、归档等事件往项目群弹一条消息，不用等维修员自己打开钉钉。

配置（backend/.env）：
    DINGTALK_GROUP_WEBHOOK=https://oapi.dingtalk.com/robot/send?access_token=xxx
    DINGTALK_GROUP_SECRET=SECxxxxxxxx            # 群机器人「加签」密钥，建议配上

发送失败只记日志，绝不影响主业务；调用 send_*_async 时走后台线程，不阻塞接口。
"""
import base64
import hashlib
import hmac
import threading
import time
import urllib.parse
from typing import Dict, List, Optional

import requests
from loguru import logger

from app.core.config import settings

EVENT_TITLES = {
    "created": "🆕 新工单",
    "submitted": "📮 报修已提交",
    "assigned": "👷 工单已派工",
    "archived": "✅ 工单已归档",
    "rejected": "⛔ 工单被退回",
}


class DingTalkGroupRobot:
    """自定义群机器人客户端（text / markdown / actionCard）"""

    def __init__(self) -> None:
        self.timeout = float(getattr(settings, "DINGTALK_GROUP_TIMEOUT", 6))

    # ---------- 配置 ----------
    @property
    def webhook(self) -> str:
        return (getattr(settings, "DINGTALK_GROUP_WEBHOOK", "") or "").strip()

    @property
    def secret(self) -> str:
        return (getattr(settings, "DINGTALK_GROUP_SECRET", "") or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self.webhook)

    def masked_webhook(self) -> str:
        url = self.webhook
        if not url:
            return ""
        token = urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get("access_token", [""])[0]
        if token:
            return url.replace(token, token[:4] + "****" + token[-4:] if len(token) > 8 else "****")
        return url[:40] + "…"

    # ---------- 签名 ----------
    def signed_url(self) -> str:
        """群机器人加签：sign = base64(HMAC-SHA256(secret, timestamp + '\\n' + secret))"""
        url = self.webhook
        if not self.secret:
            return url
        ts = str(round(time.time() * 1000))
        string_to_sign = f"{ts}\n{self.secret}"
        digest = hmac.new(self.secret.encode("utf-8"),
                          string_to_sign.encode("utf-8"),
                          hashlib.sha256).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(digest))
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}timestamp={ts}&sign={sign}"

    # ---------- 发送 ----------
    def _post(self, payload: Dict) -> Dict:
        if not self.enabled:
            return {"ok": False, "skipped": "未配置 DINGTALK_GROUP_WEBHOOK"}
        try:
            resp = requests.post(self.signed_url(), json=payload, timeout=self.timeout)
            data = resp.json() if resp.text else {}
        except Exception as e:
            logger.warning(f"[GroupRobot] 推送异常: {e}")
            return {"ok": False, "error": str(e)}
        if data.get("errcode") not in (0, None):
            logger.warning(f"[GroupRobot] 推送被拒: {data}")
            return {"ok": False, "resp": data}
        logger.info(f"[GroupRobot] 推送成功: {payload.get('msgtype')}")
        return {"ok": True, "resp": data}

    def send_markdown(self, title: str, text: str,
                      at_mobiles: Optional[List[str]] = None,
                      at_all: bool = False) -> Dict:
        payload = {
            "msgtype": "markdown",
            "markdown": {"title": title, "text": text},
            "at": {"atMobiles": at_mobiles or [], "isAtAll": at_all},
        }
        return self._post(payload)

    def send_text(self, content: str,
                  at_mobiles: Optional[List[str]] = None,
                  at_all: bool = False) -> Dict:
        payload = {
            "msgtype": "text",
            "text": {"content": content},
            "at": {"atMobiles": at_mobiles or [], "isAtAll": at_all},
        }
        return self._post(payload)

    def send_markdown_async(self, title: str, text: str,
                            at_mobiles: Optional[List[str]] = None,
                            at_all: bool = False) -> None:
        """后台线程发送：接口响应不受群机器人网络耗时影响"""
        if not self.enabled:
            return
        threading.Thread(
            target=self.send_markdown,
            args=(title, text),
            kwargs={"at_mobiles": at_mobiles, "at_all": at_all},
            daemon=True,
        ).start()

    # ---------- 业务事件 ----------
    def work_order_event(self, event: str, wo: Dict, extra: str = "") -> None:
        """工单事件推送

        wo: {id, work_order_no, device_code, fault_description, priority, location,
             status, technician_name, reporter_name}
        """
        if not self.enabled:
            return
        title = EVENT_TITLES.get(event, "工单更新")
        base = (getattr(settings, "SERVER_PUBLIC_URL", "") or "").rstrip("/")
        link = f"{base}/work-orders/{wo.get('id')}" if base and wo.get("id") else ""

        lines = [f"### {title} {wo.get('work_order_no') or ''}", ""]
        if wo.get("device_code"):
            lines.append(f"- **设备**：{wo['device_code']}")
        if wo.get("fault_description"):
            desc = str(wo["fault_description"]).replace("\n", " ")[:80]
            lines.append(f"- **故障**：{desc}")
        if wo.get("priority"):
            lines.append(f"- **优先级**：{wo['priority']}")
        if wo.get("location"):
            lines.append(f"- **位置**：{wo['location']}")
        if wo.get("technician_name"):
            lines.append(f"- **维修员**：{wo['technician_name']}")
        if wo.get("reporter_name"):
            lines.append(f"- **报修人**：{wo['reporter_name']}")
        if extra:
            lines.append(f"- **说明**：{extra}")
        if link:
            lines.append("")
            lines.append(f"> [查看工单详情]({link})")

        self.send_markdown_async(title, "\n".join(lines))

    # ---------- 库存预警 ----------
    def stock_alert_event(self, part_code: str, part_name: str, stock: float,
                          safety_stock: float, unit: str = "",
                          location: str = "", operator: str = "") -> None:
        """库存跌破安全库存时推一条：只在「这次出库刚好跌破」时调用，避免重复刷屏"""
        if not self.enabled:
            return
        title = "备件库存预警"
        lines = [f"### {title}", "", f"- **备件**：{part_code} {part_name}".rstrip()]
        lines.append(f"- **当前库存**：{stock:g}{(' ' + unit) if unit else ''}"
                     f"（安全库存 {safety_stock:g}）")
        if location:
            lines.append(f"- **存放位置**：{location}")
        if operator:
            lines.append(f"- **触发人**：{operator}")
        lines.append("")
        lines.append("> 请及时补货，避免维修时无件可换")
        self.send_markdown_async(title, "\n".join(lines))

    # ---------- 请假审批 ----------
    def leave_event(self, event: str, lr: Dict, extra: str = "") -> None:
        """lr: {id, requester_name, leave_type, start_date, end_date, days, approver_comment}"""
        if not self.enabled:
            return
        title = {
            "submitted": "新的请假申请待审批",
            "approved": "请假申请已批准",
            "rejected": "请假申请已驳回",
            "cancelled": "请假申请已撤销",
        }.get(event, "请假申请更新")

        lines = [f"### {title}", ""]
        if lr.get("requester_name"):
            lines.append(f"- **申请人**：{lr['requester_name']}")
        if lr.get("leave_type"):
            lines.append(f"- **类型**：{lr['leave_type']}")
        if lr.get("start_date") or lr.get("end_date"):
            span = f"{lr.get('start_date') or ''} ~ {lr.get('end_date') or ''}".strip(" ~")
            if lr.get("days"):
                span += f"（{lr['days']:g} 天）"
            lines.append(f"- **时间**：{span}")
        if lr.get("approver_comment"):
            lines.append(f"- **审批意见**：{lr['approver_comment']}")
        if extra:
            lines.append(f"- **说明**：{extra}")
        self.send_markdown_async(title, "\n".join(lines))


group_robot = DingTalkGroupRobot()

"""站内通知 WebSocket 连接管理

同步业务代码（FastAPI 普通 def 接口）通过 notify_user() 投递，
内部用 run_coroutine_threadsafe 切回主事件循环发送，不阻塞业务线程。
"""
import asyncio
from typing import Dict, Set

from fastapi import WebSocket


class NotificationConnectionManager:
    def __init__(self):
        self._connections: Dict[int, Set[WebSocket]] = {}
        self._loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, user_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket) -> None:
        conns = self._connections.get(user_id)
        if not conns:
            return
        conns.discard(websocket)
        if not conns:
            self._connections.pop(user_id, None)

    async def send_to_user(self, user_id: int, message: dict) -> None:
        for ws in list(self._connections.get(user_id, ())):
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(user_id, ws)

    def notify_user(self, user_id: int, message: dict) -> None:
        """从同步代码投递（没有事件循环/没有连接时静默跳过）"""
        if not user_id or not self._loop or not self._loop.is_running():
            return
        if not self._connections.get(user_id):
            return
        try:
            asyncio.run_coroutine_threadsafe(self.send_to_user(user_id, message), self._loop)
        except Exception:
            pass

    def online_count(self) -> int:
        return sum(len(v) for v in self._connections.values())


manager = NotificationConnectionManager()

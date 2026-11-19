"""事件总线:把后端发生的事推给所有连着的前端(SSE)。"""

import asyncio
import contextlib

from fix_mate.domain.models import ChangedEvent, ServerEvent

#: 「数据变了」事件的合并窗口。窗口内无论变化多少次,前端只收到一条,避免重复刷新。
CHANGED_COALESCE_SECONDS = 0.15


class EventBus:
    def __init__(self, coalesce_seconds: float = CHANGED_COALESCE_SECONDS):
        self._subscribers: set[asyncio.Queue[ServerEvent]] = set()
        self._coalesce_seconds = coalesce_seconds
        self._changed_pending = False

    def subscribe(self) -> asyncio.Queue[ServerEvent]:
        queue: asyncio.Queue[ServerEvent] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[ServerEvent]) -> None:
        self._subscribers.discard(queue)

    def publish(self, event: ServerEvent) -> None:
        """立即推送给所有订阅者。"""
        for queue in self._subscribers:
            queue.put_nowait(event)

    def changed(self) -> None:
        """通知前端数据变了。短时间内多次调用会合并成一条。"""
        if self._changed_pending:
            return
        self._changed_pending = True
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:  # 不在事件循环里(同步测试),直接发
            self._flush_changed()
            return
        loop.call_later(self._coalesce_seconds, self._flush_changed)

    def _flush_changed(self) -> None:
        self._changed_pending = False
        self.publish(ChangedEvent())

    async def flush(self) -> None:
        """测试用:等合并窗口过去。"""
        with contextlib.suppress(Exception):
            await asyncio.sleep(self._coalesce_seconds * 1.5)

"""定时从飞书拉取分配给用户的缺陷。

新缺陷默认不在任何清单里,并通知用户归类。已经存在的缺陷不会被覆盖(它的处理状态以本地为准)。
拉取失败(网络、授权过期)会越来越慢地重试,不会刷屏,也不会让服务崩溃。
"""

import asyncio
import contextlib
import logging

from fix_mate.engine.external import Feishu
from fix_mate.services.commands import Commands

log = logging.getLogger(__name__)

#: 失败后重试间隔的上限
MAX_BACKOFF_SECONDS = 15 * 60


class FeishuPoller:
    def __init__(self, feishu: Feishu, commands: Commands, interval: float):
        self._feishu = feishu
        self._commands = commands
        self._interval = interval
        self._task: asyncio.Task | None = None

    async def poll_once(self) -> int:
        """拉取一次,返回新增了几条缺陷。"""
        return await self._commands.import_defects(await self._feishu.fetch_assigned())

    def start(self) -> None:
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _run(self) -> None:
        failures = 0
        while True:
            try:
                await self.poll_once()
                failures = 0
            except Exception:  # 拉取失败只记日志并退避,不能让轮询任务死掉(取消不会被这里捕获)
                failures += 1
                log.warning("从飞书拉取缺陷失败(第 %d 次),稍后重试", failures, exc_info=True)
            await asyncio.sleep(min(self._interval * 2**failures, MAX_BACKOFF_SECONDS) if failures else self._interval)

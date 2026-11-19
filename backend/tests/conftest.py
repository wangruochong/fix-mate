from datetime import UTC, datetime

from fix_mate.domain.models import Defect, DefectState, ListRecord

NOW = datetime(2026, 11, 19, 8, 0, tzinfo=UTC)


def make_defect(id: str, state: DefectState = "queued", **kw) -> Defect:
    base = dict(
        id=id, title=id, type="Bug", priority="Major", requirement="r", version="v",
        reporter="x", created_at=NOW, description="", state=state,
    )  # fmt: skip
    return Defect(**{**base, **kw})


def make_list(id: str, defect_ids: list[str], *, on: bool = True, seq: int = 1, urgent: bool = False) -> ListRecord:
    return ListRecord(id=id, name=id, urgent=urgent, created_at=NOW, on=on, seq=seq, defect_ids=defect_ids)


def by_id(*defects: Defect) -> dict[str, Defect]:
    return {d.id: d for d in defects}


# ---------------------------------------------------------------- 服务层的测试装配

import asyncio  # noqa: E402
import random  # noqa: E402
from dataclasses import dataclass  # noqa: E402

import pytest  # noqa: E402

from fix_mate.domain.models import ServerEvent  # noqa: E402
from fix_mate.engine.stub import StubExecutor  # noqa: E402
from fix_mate.seed import seed_defects, seed_lists  # noqa: E402
from fix_mate.services.commands import Commands  # noqa: E402
from fix_mate.services.events import EventBus  # noqa: E402
from fix_mate.services.notifier import Notifier  # noqa: E402
from fix_mate.services.scheduler import Scheduler  # noqa: E402
from fix_mate.store.db import open_database  # noqa: E402
from fix_mate.store.repository import Repository  # noqa: E402


@dataclass
class World:
    """一套完整的后端(内存数据库 + 手动节奏的模拟执行器),测试直接驱动它。"""

    repo: Repository
    executor: StubExecutor
    scheduler: Scheduler
    commands: Commands
    bus: EventBus
    events: list[ServerEvent]

    async def advance(self, steps: int = 1) -> None:
        """让 AI 前进 steps 步,并等所有后续处理完成。"""
        for _ in range(steps):
            self.executor.advance()
            await self.settle()

    async def settle(self) -> None:
        """等执行器的回调和调度都处理完。"""
        for _ in range(4):
            for _ in range(10):
                await asyncio.sleep(0)
            await self.scheduler.drain()

    async def wait_until(self, predicate, timeout: float = 3.0) -> None:
        """等后台任务(接受、复核)完成。"""
        deadline = asyncio.get_running_loop().time() + timeout
        while not predicate():
            assert asyncio.get_running_loop().time() < deadline, "等待超时"
            await asyncio.sleep(0.005)
        await self.settle()

    def defect(self, defect_id: str):
        d = self.repo.get_defect(defect_id)
        assert d is not None
        return d

    def list_state(self, list_id: str) -> str:
        return next(x.state for x in self.commands.lists() if x.id == list_id)

    def notifications(self):
        return self.repo.notifications()


@pytest.fixture
async def world():
    repo = Repository(open_database(":memory:"))
    with repo.transaction():
        for d in seed_defects():
            repo.save_defect(d)
        for r in seed_lists():
            repo.save_list(r)
    bus = EventBus(coalesce_seconds=0)
    events: list[ServerEvent] = []
    bus.subscribe  # noqa: B018
    queue = bus.subscribe()
    executor = StubExecutor(interval=None, speed=1000, seed=1)
    notifier = Notifier(repo, bus, lambda: NOW)
    scheduler = Scheduler(repo, executor, bus, notifier, lambda: NOW, rng=random.Random(1))
    commands = Commands(repo, scheduler, executor, executor, bus, notifier, lambda: NOW)
    w = World(repo, executor, scheduler, commands, bus, events)
    await scheduler.start()
    await w.settle()
    yield w
    while not queue.empty():
        events.append(queue.get_nowait())
    await commands.shutdown()
    await scheduler.stop()

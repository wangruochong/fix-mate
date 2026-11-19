"""调度器:让执行器始终在处理「该处理的那个缺陷」。

分工:
- `domain/schedule.py` 的 `decide()` 回答「现在该暂停谁、该开始谁」(纯规则)。
- 本文件负责**执行**这个结论:暂停执行器里的任务、启动新的、把结果写进数据库。
- `services/commands.py` 是用户的操作入口,改完数据后调用 `reconcile()`。

并发约定(整个后端只有这一处需要小心):
1. 所有会修改缺陷或清单的操作,都必须持有 `self.lock`。
2. 执行器的回调(进度、完成)**不直接改数据**,而是放进消息队列,由一个消费协程拿到锁后依次处理。
   这样执行器永远不会因为等锁而卡住,也就不会和「暂停时等执行器停下」互相死等。
3. 每次处理都有 run_id。暂停后到达的旧回调,run_id 对不上,直接丢弃。
"""

import asyncio
import contextlib
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fix_mate.domain.models import (
    CachedConclusion,
    CodeSegment,
    Defect,
    ListRecord,
    ListState,
    Passed,
    PauseCause,
    PauseInfo,
    RichText,
)
from fix_mate.domain.schedule import Start, active_list, decide, list_state
from fix_mate.engine.ports import Failed, Fixed, Runner, RunRef, RunResult, Skipped
from fix_mate.services.events import EventBus
from fix_mate.services.notifier import Notifier
from fix_mate.store.repository import Repository

log = logging.getLogger(__name__)


# ---------------------------------------------------------------- 执行器发来的消息


@dataclass(frozen=True)
class _StepStarted:
    run: RunRef
    step: int


@dataclass(frozen=True)
class _Rebased:
    run: RunRef


@dataclass(frozen=True)
class _Finished:
    run: RunRef


_Message = _StepStarted | _Rebased | _Finished

#: 还没有记录过「上一次的活跃清单」(刚启动),此时的变化不发通知
_UNSET = object()


def plain_text(text: RichText) -> str:
    """富文本转成纯文字,用在缓存的结论摘要里。"""
    return "".join(s if isinstance(s, str) else s.code if isinstance(s, CodeSegment) else s.bold for s in text)


class Scheduler:
    def __init__(
        self,
        repo: Repository,
        runner: Runner,
        bus: EventBus,
        notifier: Notifier,
        clock: Callable[[], datetime],
        rng: random.Random | None = None,
    ):
        self._repo = repo
        self._runner = runner
        self._bus = bus
        self._notifier = notifier
        self._clock = clock
        self._rng = rng or random.Random()

        self.lock = asyncio.Lock()
        self._messages: asyncio.Queue[_Message] = asyncio.Queue()
        self._consumer: asyncio.Task | None = None
        self._current: RunRef | None = None
        #: 执行器已经汇报、但还没被消费协程处理的结果。暂停时要先看这里,见 pause_now
        self._results: dict[RunRef, RunResult] = {}
        self._run_seq = 0
        self._last_active_id: object = _UNSET
        self._last_states: dict[str, ListState] = {}

    # ---------------------------------------------------------------- 生命周期

    async def start(self) -> None:
        """启动时调用:收拾上次异常退出留下的现场,然后开始调度。"""
        self._consumer = asyncio.create_task(self._consume())
        async with self.lock:
            self.recover_interrupted()
            self.remember_transitions()
            await self.reconcile()

    async def stop(self) -> None:
        if self._consumer:
            self._consumer.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._consumer
        await self._runner.shutdown()

    def recover_interrupted(self) -> None:
        """上次进程异常退出时,数据库里可能还有「AI 处理中」的缺陷,但执行器里已经没有任务了。
        统一改成「被插队而暂停」:调度会自动让它们从暂停处恢复。"""
        for d in self._repo.all_defects():
            if d.state == "analyzing":
                self._mark_paused(d, "preempted")

    async def discard_progress(self, defect_id: str) -> None:
        """丢弃一个缺陷的一切处理进度。调用者必须持有 `self.lock`,并保证它此刻没有在处理。"""
        await self._runner.discard(defect_id)

    async def halt(self) -> None:
        """停掉正在进行的处理,不保存进度。用于重置数据。"""
        if self._current:
            await self._runner.pause(self._current)
            self._current = None
        self._results.clear()
        self._last_active_id = _UNSET
        self._last_states.clear()

    # ---------------------------------------------------------------- 执行器的回调(只入队,不碰数据)

    def step_started(self, run: RunRef, step: int) -> None:
        self._messages.put_nowait(_StepStarted(run, step))

    def rebased(self, run: RunRef) -> None:
        self._messages.put_nowait(_Rebased(run))

    def finished(self, run: RunRef, result: RunResult) -> None:
        # 结果同步登记,消息只是通知「该去处理了」。这样即使暂停请求抢在消息被处理之前到达,
        # 也不会把已经做完的修复丢掉(见 pause_now)
        self._results[run] = result
        self._messages.put_nowait(_Finished(run))

    async def drain(self) -> None:
        """测试用:等消息队列里已有的消息都处理完。"""
        await self._messages.join()

    async def _consume(self) -> None:
        while True:
            message = await self._messages.get()
            try:
                async with self.lock:
                    await self._handle(message)
            except Exception:
                log.exception("处理执行器消息失败:%s", message)
            finally:
                self._messages.task_done()

    async def _handle(self, message: _Message) -> None:
        if message.run != self._current:
            return  # 过期的回调:这次处理早已被暂停或替换
        defect = self._repo.get_defect(message.run.defect_id)
        if defect is None:
            return
        match message:
            case _StepStarted(step=step):
                defect.step = step
                self._repo.save_defect(defect)
                self._bus.changed()
            case _Rebased():
                defect.rebased = True
                self._repo.save_defect(defect)
                self._bus.changed()
            case _Finished(run=run):
                result = self._results.pop(run, None)
                if result is None:  # 已经在暂停流程里按结果处理过了
                    return
                self._current = None
                self._apply_result(defect, result)
                await self.reconcile()

    def _apply_result(self, defect: Defect, result: RunResult) -> None:
        defect.step = None
        match result:
            case Fixed(fix=fix, base_commit=base):
                defect.state = "review"
                defect.rebased = None
                defect.fix = fix
                # 修好时如果同清单里还有别的待审核方案,它们可能互相影响,要复核
                defect.needs_recheck = self._shares_list_with_review(defect)
                if defect.needs_recheck:
                    defect.cached = CachedConclusion(
                        at=self._clock(), base_commit=base, text=plain_text(fix.conclusion)
                    )
                self._notifier.notify(f"方案已就绪 · {defect.id}", defect.title, "new", defect.id)
            case Skipped(reason=reason):
                defect.state = "passed"
                defect.outcome = Passed(auto=True, reason=reason)
                self._notifier.notify(f"AI 已跳过 {defect.id}", "不是可通过改代码解决的确定问题", "skip", defect.id)
            case Failed(message=message):
                # 出错的缺陷暂停,原因留给用户,需要用户手动继续(失败状态的完整设计还没定)
                self._mark_paused(defect, "user", note=f"处理出错:{message}")
                self._notifier.notify(f"处理 {defect.id} 时出错", message, "warn", defect.id)
                return
        self._repo.save_defect(defect)

    def _shares_list_with_review(self, defect: Defect) -> bool:
        others = {d.id: d for d in self._repo.all_defects() if d.state == "review" and d.id != defect.id}
        return any(
            any(i in others for i in record.defect_ids)
            for record in self._repo.all_lists()
            if defect.id in record.defect_ids
        )

    # ---------------------------------------------------------------- 核心:让现实符合决策

    async def reconcile(self) -> None:
        """根据最新数据重新决策并执行。调用者必须持有 `self.lock`。

        每次状态可能变化之后都要调用:用户操作、缺陷处理完成、收到新缺陷。
        """
        while True:
            lists = self._repo.all_lists()
            defects = {d.id: d for d in self._repo.all_defects()}
            decision = decide(lists, defects)
            if decision.pauses:
                for pause in decision.pauses:
                    await self.pause_now(defects[pause.defect_id], pause.cause)
                continue  # 旧的停下之后,再决定一次
            if decision.start:
                self._start(decision.start, defects[decision.start.defect_id])
            break
        self._announce_transitions()
        self._bus.changed()

    async def pause_now(self, defect: Defect, cause: PauseCause) -> None:
        """立刻让一个正在处理的缺陷暂停:先让执行器停下,再记录暂停。"""
        fresh = self._repo.get_defect(defect.id) or defect
        run = self._current
        if run and run.defect_id == defect.id:
            await self._runner.pause(run)
            self._current = None
            # 暂停请求到达时,这次处理可能恰好已经做完。结果丢不得:按结果处理,不再暂停。
            result = self._results.pop(run, None)
            if result is not None:
                self._apply_result(fresh, result)
                return
        self._mark_paused(fresh, cause)

    def _mark_paused(self, defect: Defect, cause: PauseCause, note: str | None = None) -> None:
        defect.state = "paused"
        defect.pause = PauseInfo(
            cause=cause,
            at=self._clock(),
            note=note,
            confidence=86 + self._rng.randrange(10) if (defect.step or 0) >= 1 else None,
        )
        self._repo.save_defect(defect)

    def _start(self, start: Start, defect: Defect) -> None:
        snapshot = defect.model_copy(deep=True)  # 给执行器的是启动前的样子,里面有暂停信息
        if not start.resume:
            defect.step = 0
        defect.pause = None
        defect.state = "analyzing"
        self._repo.save_defect(defect)
        self._run_seq += 1
        self._current = RunRef(defect.id, self._run_seq)
        self._runner.start(self._current, snapshot, start.resume, self)

    # ---------------------------------------------------------------- 状态变化时的通知

    def remember_transitions(self) -> None:
        """记住当前状态作为基线,之后的变化才发通知。"""
        lists = self._repo.all_lists()
        defects = {d.id: d for d in self._repo.all_defects()}
        active = active_list(lists, defects)
        self._last_active_id = active.id if active else None
        self._last_states = {r.id: list_state(r, lists, defects) for r in lists}

    def _announce_transitions(self) -> None:
        lists = self._repo.all_lists()
        defects = {d.id: d for d in self._repo.all_defects()}
        active = active_list(lists, defects)
        active_id = active.id if active else None
        if self._last_active_id is not _UNSET and active_id != self._last_active_id:
            last = next((r for r in lists if r.id == self._last_active_id), None)
            if active and active.urgent:
                self._notifier.notify("紧急处理中", "AI 已切换去处理紧急缺陷,其它清单暂时让位,进度已保存", "warn")
            elif last and last.urgent and active:
                self._notifier.notify(
                    f"已自动恢复「{active.name}」", "紧急缺陷处理完成,从上次暂停处继续", "ok", quiet=True
                )
        self._last_active_id = active_id

        for record in lists:
            state = list_state(record, lists, defects)
            previous = self._last_states.get(record.id)
            if previous is not None and previous != state and state == "done" and previous != "pending":
                self._notify_list_done(record, defects)
            self._last_states[record.id] = state

    def _notify_list_done(self, record: ListRecord, defects: dict[str, Defect]) -> None:
        waiting = sum(1 for i in record.defect_ids if i in defects and defects[i].state == "review")
        title = "紧急缺陷已处理完" if record.urgent else f"「{record.name}」处理完成"
        self._notifier.notify(title, f"还有 {waiting} 个缺陷等你审核" if waiting else "都已处理完毕", "done")

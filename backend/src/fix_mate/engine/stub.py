"""定时器版的临时执行器:不碰 git、不调 AI,只按固定节奏模拟进度。

行为和前端 `web/src/mock/engine.ts` 一致,用来让前端先连上真实后端。
第 4、5 步用真正的 LangGraph 引擎替换后,这个文件就删除。

两种节奏:
- 自动:每隔 interval 秒推进一步(默认,和前端模拟一致)。
- 手动(interval=None):只在测试里调用 `advance()` 时才推进一步,结果完全可预测。
"""

import asyncio
import contextlib
import random

from fix_mate.domain.models import Defect, DiffLine, Fix, FixFile
from fix_mate.engine.ports import (
    AcceptProgress,
    AcceptResult,
    Fixed,
    RunObserver,
    RunRef,
    Skipped,
)

STEP_INTERVAL = 1.6
RECHECK_DELAY = 1.8
_FINAL_STEP = 3  # step 走到 3 就算修好了


class StubExecutor:
    def __init__(self, *, interval: float | None = STEP_INTERVAL, speed: float = 1.0, seed: int | None = None):
        self._interval = interval
        self._speed = speed
        self._random = random.Random(seed)
        self._tasks: dict[int, asyncio.Task] = {}
        self._ticks = asyncio.Semaphore(0)
        #: 模拟 main 分支的版本,每接受一个缺陷加一;暂停期间 main 变了,恢复时就要「同步最新 main」
        self.main_rev = 0
        self._paused_at_rev: dict[str, int] = {}

    # ---------------------------------------------------------------- 节奏

    async def _wait(self, seconds: float) -> None:
        await asyncio.sleep(seconds / self._speed)

    async def _wait_step(self) -> None:
        if self._interval is None:
            await self._ticks.acquire()
        else:
            await self._wait(self._interval)

    def advance(self, steps: int = 1) -> None:
        """手动模式:让正在处理的缺陷前进 steps 步。"""
        for _ in range(steps):
            self._ticks.release()

    # ---------------------------------------------------------------- Executor 接口

    def start(self, run: RunRef, defect: Defect, resume: bool, observer: RunObserver) -> None:
        self._tasks[run.run_id] = asyncio.create_task(self._process(run, defect, resume, observer))

    async def pause(self, run: RunRef) -> None:
        task = self._tasks.pop(run.run_id, None)
        self._paused_at_rev[run.defect_id] = self.main_rev
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def discard(self, defect_id: str) -> None:
        self._paused_at_rev.pop(defect_id, None)

    async def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        for task in list(self._tasks.values()):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    async def accept(self, defect: Defect, on_progress: AcceptProgress) -> AcceptResult:
        assert defect.fix is not None
        ota = f"3.8.0.{2400 + self._random.randrange(90)}"
        on_progress(0, None)
        await self._wait(0.65)
        for done in range(1, 7):
            on_progress(done, ota if done > 4 else None)
            await self._wait(1.8 if done == 4 else 0.65)
        self.main_rev += 1
        return AcceptResult(ota=ota, commit=defect.fix.commit)

    async def forget(self, defect_id: str) -> None:
        pass

    def unfinished(self) -> dict[str, int]:
        return {}

    async def recheck(self, defect: Defect) -> tuple[str, str | None]:
        await self._wait(RECHECK_DELAY)
        text = "已结合最新 main(含已合入的相关修改)与缓存结论重新评估:原方案调整为复用已有的校验函数,冲突已消除。"
        return text, self._hex(7)

    # ---------------------------------------------------------------- 模拟一次处理

    async def _process(self, run: RunRef, defect: Defect, resume: bool, observer: RunObserver) -> None:
        step = (defect.step or 0) if resume else 0
        if (
            resume
            and defect.pause
            and defect.pause.cause == "preempted"
            and self.main_rev > self._paused_at_rev.get(defect.id, 0)
        ):
            observer.rebased(run)
        while True:
            observer.step_started(run, step)
            await self._wait_step()
            step += 1
            if defect.type == "建议":  # 建议类缺陷没有确定的代码修改目标
                reason = "AI 判断:这是一条产品体验类建议,没有确定的代码修改目标,已自动跳过。如需处理请手动调整。"
                observer.finished(run, Skipped(reason))
                return
            if step >= _FINAL_STEP:
                observer.finished(run, Fixed(fix=self._make_fix(defect), base_commit="a3f9c21"))
                return

    def _hex(self, n: int) -> str:
        return "".join(f"{self._random.randrange(16):x}" for _ in range(n))

    def _make_fix(self, defect: Defect) -> Fix:
        if defect.fix:  # 种子数据里已经有方案的,沿用
            return defect.fix
        module = defect.requirement.replace(" ", "")[:8]
        return Fix(
            confidence=85 + self._random.randrange(10),
            branch=f"fixmate/{defect.id}",
            commit=self._hex(7),
            judge="问题描述明确,可通过修改代码解决。",
            summary=[["定位到相关模块并修复"], ["补充必要的测试"]],
            conclusion=["已分析根因并完成修复,详见 diff。"],
            files=[
                FixFile(
                    name=f"src/modules/{module}/index.ts",
                    additions=8,
                    deletions=3,
                    lines=[
                        DiffLine(kind="hunk", text="@@ -20,6 +20,11 @@"),
                        DiffLine(kind="del", text="-   return legacy(x)"),
                        DiffLine(kind="add", text="+   return safe(x)"),
                    ],
                )
            ],
            conflicts=[],
        )


class PlaceholderRechecker:
    """复核的占位实现:等一会儿,给出一段固定说明,**不改动方案的提交**。

    复核的真实做法(基线提交、文件重叠等)等核心功能完成后再深入。在那之前,它不能碰真实的提交号。
    """

    def __init__(self, *, speed: float = 1.0):
        self._speed = speed

    async def recheck(self, defect: Defect) -> tuple[str, str | None]:
        await asyncio.sleep(RECHECK_DELAY / self._speed)
        return "已结合最新 main 与缓存结论重新评估,方案没有需要调整的地方。", None

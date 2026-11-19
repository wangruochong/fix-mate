"""调度器和「真正干活的执行器」之间的边界。

调度器只关心「现在该处理哪个缺陷」,执行器负责把它处理完。两边只通过这里的类型沟通,
所以执行器可以替换:开发早期是定时器模拟(engine/stub.py),现在是 LangGraph + Claude Code。
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from fix_mate.domain.models import Defect, Fix


@dataclass(frozen=True)
class RunRef:
    """一次处理的标识。同一个缺陷暂停后再恢复是新的一次,所以带 run_id,用来丢弃过期的回调。"""

    defect_id: str
    run_id: int


# ---------------------------------------------------------------- 处理结果


@dataclass(frozen=True)
class Fixed:
    """AI 修好了,等用户审核。"""

    fix: Fix
    #: 方案基于哪个 main 提交,复核时用
    base_commit: str


@dataclass(frozen=True)
class Skipped:
    """AI 判断不是改代码能解决的确定问题,自动跳过。"""

    reason: str


@dataclass(frozen=True)
class Failed:
    """处理出错了。缺陷会暂停,原因交给用户。"""

    message: str


RunResult = Fixed | Skipped | Failed


class RunObserver(Protocol):
    """执行器通过它汇报进度。方法都是同步且不阻塞的,执行器不会因此被调度器卡住。"""

    def step_started(self, run: RunRef, step: int) -> None:
        """开始做第 step 步(0 判断、1 建分支、2 改代码)。"""

    def rebased(self, run: RunRef) -> None:
        """恢复时已把临时分支同步到最新 main。"""

    def finished(self, run: RunRef, result: RunResult) -> None:
        """这次处理结束了。被暂停的不会调用它。"""


# ---------------------------------------------------------------- 接受流程


@dataclass(frozen=True)
class AcceptResult:
    ota: str
    commit: str


#: 接受流程的进度回调:(已完成的步骤数, 已知的 OTA 版本号)
AcceptProgress = Callable[[int, str | None], None]


class Runner(Protocol):
    """把缺陷一个个处理完的执行器。同一时间只有一个在运行。"""

    def start(self, run: RunRef, defect: Defect, resume: bool, observer: RunObserver) -> None:
        """开始或恢复处理一个缺陷。立即返回,在后台执行,通过 observer 汇报。

        defect 是启动前的快照:恢复时它的 `step` 是上次停下的步骤,`pause` 说明为什么停。
        """

    async def pause(self, run: RunRef) -> None:
        """让这次处理停下来并保存进度。返回时它已经确实停了。

        如果这次处理其实已经结束,它的结果已经通过 `observer.finished` 汇报过了,调用方要自己处理这种情况。
        """

    async def discard(self, defect_id: str) -> None:
        """忘掉这个缺陷的一切进度(检查点、分支、工作目录)。用于拒绝并丢弃、重置数据。没有则忽略。"""

    async def shutdown(self) -> None:
        """程序退出时停掉所有后台任务。"""


class AcceptFailed(Exception):
    """接受流程在某一步失败了。缺陷保持待审核,用户再点接受会从这一步继续。"""

    def __init__(self, step: int, message: str):
        super().__init__(message)
        self.step = step
        self.message = message


class Accepter(Protocol):
    async def accept(self, defect: Defect, on_progress: AcceptProgress) -> AcceptResult:
        """执行接受流程的 7 步。失败时抛出 AcceptFailed。"""

    async def forget(self, defect_id: str) -> None:
        """接受成功、状态已保存之后调用,清掉这个缺陷的接受进度。"""

    def unfinished(self) -> dict[str, int]:
        """上次没做完的接受(程序中途退出):缺陷 -> 卡在第几步。"""


class Rechecker(Protocol):
    async def recheck(self, defect: Defect) -> tuple[str, str | None]:
        """复核一个待审核的方案,返回 (复核结果说明, 方案有变化时的新提交号;没有变化就是 None)。"""

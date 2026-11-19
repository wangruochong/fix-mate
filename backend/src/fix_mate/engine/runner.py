"""运行器:启动、暂停、恢复修复图,并把图的进度汇报给调度器。

和调度器的分工:调度器决定「该处理哪个缺陷」,运行器负责「把它处理完」(见 ports.py 的 Runner)。

一次处理的生命周期:

    start ──▶ 后台任务 _run ──▶ 跑图 ──▶ 完成 ──▶ observer.finished(结果)
                  │
     pause ──▶ 设置暂停信号 ──▶ 节点发现信号并停下 ──▶ 保存进度(临时提交、删目录) ──▶ pause 返回
                              (停得太慢,超时后强制取消作为兜底)

汇报给调度器的事:
- 每个节点**开始**时汇报第几步(这样界面显示的是「正在做」,而不是「刚做完」);
- 恢复时分支被同步到了最新 main;
- 处理结束(修好了、不可修复、出错)。被暂停的不会汇报结束。
"""

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from langgraph.checkpoint.base import BaseCheckpointSaver

from fix_mate.domain.models import Defect, Fix
from fix_mate.engine.external import CodeFixer, SessionStore, Workspace
from fix_mate.engine.fix_graph import (
    STEP_OF_NODE,
    FixNodes,
    FixState,
    PauseRequested,
    build_fix_graph,
    rich_from_json,
    rich_list_from_json,
)
from fix_mate.engine.ports import Failed, Fixed, RunObserver, RunRef, RunResult, Skipped

log = logging.getLogger(__name__)

#: 要求暂停后,最多等多久让它自己停下。超时就强制取消(只是兜底,正常情况下 AI 会在几秒内停下)
DEFAULT_PAUSE_TIMEOUT_SECONDS = 30


@dataclass
class _ActiveRun:
    task: asyncio.Task
    pause_signal: asyncio.Event


class GraphRunner:
    def __init__(
        self,
        *,
        fixer: CodeFixer,
        workspace: Workspace,
        sessions: SessionStore,
        checkpointer: BaseCheckpointSaver,
        load_defect: Callable[[str], Defect],
        repo_dir: Path,
        pause_timeout: float = DEFAULT_PAUSE_TIMEOUT_SECONDS,
    ):
        self._fixer = fixer
        self._workspace = workspace
        self._sessions = sessions
        self._checkpointer = checkpointer
        self._load_defect = load_defect
        self._repo_dir = repo_dir
        self._pause_timeout = pause_timeout
        self._active: dict[int, _ActiveRun] = {}

    # ------------------------------------------------------------ Runner 接口

    def start(self, run: RunRef, defect: Defect, resume: bool, observer: RunObserver) -> None:
        pause_signal = asyncio.Event()
        task = asyncio.create_task(self._run(run, resume, observer, pause_signal))
        self._active[run.run_id] = _ActiveRun(task, pause_signal)

    async def pause(self, run: RunRef) -> None:
        active = self._active.get(run.run_id)
        if active is None:  # 这次处理已经结束了
            return
        active.pause_signal.set()
        try:
            await asyncio.wait_for(asyncio.shield(active.task), self._pause_timeout)
        except TimeoutError:
            log.warning("%s 在 %ss 内没有停下,强制取消", run.defect_id, self._pause_timeout)
            active.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await active.task

    async def discard(self, defect_id: str) -> None:
        await self._checkpointer.adelete_thread(defect_id)
        await self._workspace.discard(defect_id)

    async def shutdown(self) -> None:
        tasks = [a.task for a in self._active.values()]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._active.clear()

    # ------------------------------------------------------------ 一次处理

    async def _run(self, run: RunRef, resume: bool, observer: RunObserver, pause_signal: asyncio.Event) -> None:
        try:
            result = await self._drive_graph(run, resume, observer, pause_signal)
        except PauseRequested:
            await self._save_progress(run)  # 正常暂停:把做到一半的修改存起来
            return
        except asyncio.CancelledError:
            await asyncio.shield(self._save_progress(run))  # 被强制取消:也尽力保存
            raise
        except Exception as e:  # 出错:保存已有的成果,汇报失败,原因交给用户
            log.exception("处理 %s 失败", run.defect_id)
            await self._save_progress(run)
            observer.finished(run, Failed(str(e) or type(e).__name__))
            return
        finally:
            self._active.pop(run.run_id, None)
        observer.finished(run, result)

    async def _drive_graph(
        self, run: RunRef, resume: bool, observer: RunObserver, pause_signal: asyncio.Event
    ) -> RunResult:
        nodes = FixNodes(
            fixer=self._fixer,
            workspace=self._workspace,
            sessions=self._sessions,
            load_defect=self._load_defect,
            repo_dir=self._repo_dir,
            pause=pause_signal,
        )
        graph = build_fix_graph(nodes, self._checkpointer)
        config = {"configurable": {"thread_id": run.defect_id}}

        graph_input = await self._graph_input(config, run.defect_id, resume)
        async for event in graph.astream(graph_input, config, stream_mode="tasks"):
            self._report_progress(event, run, observer)

        final = (await graph.aget_state(config)).values
        return await self._result_from(final)

    async def _graph_input(self, config: dict, defect_id: str, resume: bool) -> FixState:
        """恢复:保留检查点里已有的状态(图的入口会据此跳过已完成的判断)。
        从头开始:先清掉旧的检查点。「要求恢复但检查点已经没了」(比如演示数据)也没关系,
        那时状态是空的,自然从判断开始;工作目录和分支是可重复准备的,会沿用已有的。
        """
        if not resume:
            await self._checkpointer.adelete_thread(config["configurable"]["thread_id"])
        return {"defect_id": defect_id}

    def _report_progress(self, event: dict, run: RunRef, observer: RunObserver) -> None:
        """把图的「任务」事件翻译成调度器关心的进度。"""
        if "input" in event:  # 节点开始
            observer.step_started(run, STEP_OF_NODE[event["name"]])
        elif (event.get("result") or {}).get("rebased"):  # 节点结束,且分支被同步到了最新 main
            observer.rebased(run)

    async def _result_from(self, final: FixState) -> RunResult:
        if not final["fixable"]:
            return Skipped(f"AI 判断:{final['judge']}已自动跳过。如需处理请手动调整。")
        fix = Fix(
            confidence=final["confidence"],
            branch=final["branch"],
            commit=final["commit"],
            judge=final["judge"],
            summary=rich_list_from_json(final["summary"]),
            conclusion=rich_from_json(final["conclusion"]),
            files=await self._workspace.diff(final["base_commit"], final["commit"]),
            conflicts=[],
        )
        return Fixed(fix=fix, base_commit=final["base_commit"])

    async def _save_progress(self, run: RunRef) -> None:
        """把工作目录里没提交的修改存成临时提交并删除目录。失败只记日志:这里出错不能再影响暂停本身。"""
        try:
            await self._workspace.save_progress(run.defect_id)
        except Exception:
            log.exception("保存 %s 的进度失败", run.defect_id)

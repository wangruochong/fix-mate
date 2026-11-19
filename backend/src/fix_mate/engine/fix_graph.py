"""修复图:AI 修复一个缺陷的完整流程。

    START ─▶ assess ──可修复──▶ prepare_workspace ─▶ write_code ─▶ collect_result ─▶ END
      │         │                       ▲
      │         └──不可修复──▶ END       │
      └───已经判断过可修复(恢复时)───────┘

四个节点,每个只做一件事:

    assess             AI 只读地看代码,判断这个缺陷能不能靠改代码解决             (界面第 1 步)
    prepare_workspace  创建这个缺陷专用的 git 工作目录和分支                       (界面第 2 步)
    write_code         Claude Code 在工作目录里改代码                              (界面第 3 步)
    collect_result     把所有改动整理成一个提交,删除工作目录,只留分支            (界面第 3 步)

## 暂停和恢复

LangGraph 只能在节点之间保存进度。我们的做法(已用小实验验证,见设计文档第 10 节):

- 要暂停时,`pause` 信号被设置。节点开头检查它,设了就抛出 `PauseRequested`;
  长时间运行的 `write_code` 还会把信号交给 AI,让它在安全的地方自己停下来。
  暂停后运行器会把没提交的修改存成临时提交、**删除工作目录**(只留分支)。
- **恢复就是用同一个 thread_id 再运行一次。** 图的入口有一条条件边:已经判断过「可修复」的,
  直接从 `prepare_workspace` 开始(重新建出工作目录、同步最新 main),不用再让 AI 判断一次。
  状态里已有的判断结果会保留。

所以有一条铁律:**每个节点必须能安全地重跑**(重跑时不能出错,也不能丢掉已有的成果)。
下面每个节点的注释里都写了「重跑时会怎样」。

`collect_result` 是个例外:它很快,而且做到一半停下会留下难以收拾的状态,所以它不响应暂停,总是做完。

## 状态里放什么

检查点只放 JSON 能表示的、很小的东西(编号、路径、提交号、判断结论)。
不放 diff,也不放聊天记录;AI 的会话号放在业务库里(`SessionStore`),因为改代码被打断时节点不算完成,状态不会保存。
"""

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import TypeAdapter

from fix_mate.domain.models import Defect, RichSegment, RichText
from fix_mate.engine.external import CodeFixer, SessionStore, Workspace

#: 每个节点在界面上对应第几步(从 0 开始)。collect_result 在界面上仍算「改代码」这一步。
STEP_OF_NODE = {"assess": 0, "prepare_workspace": 1, "write_code": 2, "collect_result": 2}

# RichText 存进检查点时转成纯 JSON,读出来再还原
_RICH = TypeAdapter(RichText)
_RICH_LIST = TypeAdapter(list[RichText])


def rich_to_json(text: RichText) -> list:
    return _RICH.dump_python(text, mode="json")


def rich_list_to_json(items: list[RichText]) -> list:
    return _RICH_LIST.dump_python(items, mode="json")


def rich_from_json(data: list) -> list[RichSegment]:
    return _RICH.validate_python(data)


def rich_list_from_json(data: list) -> list[RichText]:
    return _RICH_LIST.validate_python(data)


class PauseRequested(Exception):
    """节点发现有人要求暂停。它让图停在当前节点之前,等待之后恢复。"""


class FixState(TypedDict, total=False):
    defect_id: str
    # assess 的结论
    fixable: bool
    confidence: int
    judge: str
    # prepare_workspace 的产出
    workdir: str
    branch: str
    base_commit: str
    rebased: bool
    # write_code 的产出
    summary: list
    conclusion: list
    # collect_result 的产出
    commit: str


class FixNodes:
    """图里的四个节点。依赖(改代码、git、数据库)都从构造函数传入,节点本身不碰任何外部系统的细节。"""

    def __init__(
        self,
        *,
        fixer: CodeFixer,
        workspace: Workspace,
        sessions: SessionStore,
        load_defect: Callable[[str], Defect],
        repo_dir: Path,
        pause: asyncio.Event,
    ):
        self._fixer = fixer
        self._workspace = workspace
        self._sessions = sessions
        self._load_defect = load_defect
        self._repo_dir = repo_dir
        self._pause = pause

    def _stop_if_pause_requested(self) -> None:
        if self._pause.is_set():
            raise PauseRequested

    # ------------------------------------------------------------ 节点

    async def assess(self, state: FixState) -> FixState:
        """判断缺陷能不能靠改代码解决。只读,不修改任何东西。重跑:重新判断一次,无副作用。"""
        self._stop_if_pause_requested()
        defect = self._load_defect(state["defect_id"])
        verdict = await self._fixer.assess(defect, self._repo_dir)
        return {"fixable": verdict.fixable, "confidence": verdict.confidence, "judge": verdict.reason}

    async def prepare_workspace(self, state: FixState) -> FixState:
        """创建工作目录和分支。重跑:目录或分支已存在就沿用,不会重复创建,已有的改动不丢。"""
        self._stop_if_pause_requested()
        prepared = await self._workspace.prepare(state["defect_id"])
        return {
            "workdir": str(prepared.path),
            "branch": prepared.branch,
            "base_commit": prepared.base_commit,
            "rebased": prepared.rebased,
        }

    async def write_code(self, state: FixState) -> FixState:
        """让 Claude Code 改代码。

        重跑:接着上次的 AI 会话继续,目录里已有的改动都还在,AI 不会从头来过。
        被打断时(AI 在安全的地方停下),抛出 PauseRequested,图停在本节点之前。
        """
        self._stop_if_pause_requested()
        defect = self._load_defect(state["defect_id"])
        report = await self._fixer.fix(
            defect,
            Path(state["workdir"]),
            session_id=self._sessions.get(defect.id),
            on_session=lambda session_id: self._sessions.save(defect.id, session_id),
            interrupt=self._pause,
        )
        if report.interrupted:
            raise PauseRequested
        return {"summary": rich_list_to_json(report.summary), "conclusion": rich_to_json(report.conclusion)}

    async def collect_result(self, state: FixState) -> FixState:
        """把所有改动压成一个提交,删除工作目录。

        不检查暂停信号(见文件开头的说明)。重跑:从 prepare_workspace 重新走到这里,
        压缩是「软重置到基线再整体提交」,重复做得到同样的结果。
        """
        defect = self._load_defect(state["defect_id"])
        finished = await self._workspace.finish(defect.id, f"fix: {defect.id} {defect.title}")
        return {"commit": finished.commit, "base_commit": finished.base_commit}


def route_at_start(state: FixState) -> str:
    """入口:判断过「可修复」的(恢复时)直接准备工作目录,否则从判断开始。"""
    return "prepare_workspace" if state.get("fixable") else "assess"


def route_after_assess(state: FixState) -> str:
    """不可修复的缺陷到此为止,不需要建工作目录。"""
    return "prepare_workspace" if state["fixable"] else END


def build_fix_graph(nodes: FixNodes, checkpointer: BaseCheckpointSaver) -> CompiledStateGraph:
    graph = StateGraph(FixState)
    graph.add_node("assess", nodes.assess)
    graph.add_node("prepare_workspace", nodes.prepare_workspace)
    graph.add_node("write_code", nodes.write_code)
    graph.add_node("collect_result", nodes.collect_result)

    graph.add_conditional_edges(START, route_at_start, ["assess", "prepare_workspace"])
    graph.add_conditional_edges("assess", route_after_assess, ["prepare_workspace", END])
    graph.add_edge("prepare_workspace", "write_code")
    graph.add_edge("write_code", "collect_result")
    graph.add_edge("collect_result", END)
    return graph.compile(checkpointer=checkpointer)

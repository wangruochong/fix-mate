"""接受图:用户接受一个修复方案之后的 7 个固定步骤。

    START ─▶ sync_main ─▶ cherry_pick ─▶ delete_branch ─▶ push ─▶ build_ota ─▶ mark_resolved ─▶ comment_version ─▶ END

    sync_main         切到主分支,并与远端对齐
    cherry_pick       把临时分支上的提交放进 main
    delete_branch     删除临时分支
    push              推送 main 到远端
    build_ota         调用 Jenkins 打 OTA 包,拿到版本号
    mark_resolved     在飞书把缺陷标记为已解决
    comment_version   在飞书评论里写 #版本号

## 为什么这里没有检查点

接受包含 push 和打包这类**不可撤销**的动作,所以「做到哪一步了」必须落在业务库里(`AcceptRecord`),
以业务库为准,而不是交给框架的检查点。图在这里只负责把 7 步写清楚、一步一步地报告进度。
每个节点开始前先在业务库记下「开始了」,做完记下「完成了」。

## 重试规则(接受失败后用户再点「接受」)

流程从头走一遍,但**已经完成的步骤会被跳过**。上次中断在某一步(失败或程序崩溃)时:

- 可以安全重做的步骤(切 main、放进 main、删分支、推送、标记已解决)直接重做。
  放进 main 靠 git 判断「是不是已经有了」,推送重复执行本来就没有副作用。
- **不能安全重做的步骤**(打 OTA 包会打两个包,飞书评论会重复):第一次重试被拦下,
  提示用户先去检查是否已经生效;用户再点一次,才视为确认,继续执行。
"""

from collections.abc import Awaitable, Callable
from itertools import pairwise
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from fix_mate.domain.models import AcceptRecord
from fix_mate.engine.external import AcceptProgressStore, Feishu, Jenkins, Workspace

#: 7 个步骤的名字,出现在失败提示里。顺序和图里的节点一一对应
ACCEPT_STEPS = (
    "切换到主分支",
    "把修复放进主分支",
    "删除临时分支",
    "推送到远端",
    "打 OTA 包",
    "在飞书标记为已解决",
    "在飞书评论版本号",
)

NODE_NAMES = ("sync_main", "cherry_pick", "delete_branch", "push", "build_ota", "mark_resolved", "comment_version")

#: 哪些步骤中断后可以直接重做。False 的是重做会产生重复效果的
REPEAT_SAFE = (True, True, True, True, False, True, False)

#: 不能安全重做的步骤,中断后提示用户去哪里确认
_WHERE_TO_CHECK = {4: "请先到 Jenkins 确认是否已经触发了这次打包", 6: "请先到飞书缺陷下确认是否已经有版本号评论"}


class AcceptNeedsCheck(Exception):
    """上次在一个不能安全重做的步骤中断了,需要用户确认后才能继续。"""


class AcceptState(TypedDict):
    defect_id: str
    #: 要放进 main 的修复提交(临时分支上那个)
    fix_commit: str


class AcceptNodes:
    def __init__(self, *, workspace: Workspace, jenkins: Jenkins, feishu: Feishu, progress: AcceptProgressStore):
        self._workspace = workspace
        self._jenkins = jenkins
        self._feishu = feishu
        self._progress = progress

    # ------------------------------------------------------------ 每一步

    async def sync_main(self, state: AcceptState) -> None:
        await self._step(state, 0, lambda _: self._workspace.sync_main())

    async def cherry_pick(self, state: AcceptState) -> None:
        async def act(record: AcceptRecord) -> None:
            record.picked_commit = await self._workspace.cherry_pick(state["fix_commit"])

        await self._step(state, 1, act)

    async def delete_branch(self, state: AcceptState) -> None:
        await self._step(state, 2, lambda _: self._workspace.delete_branch(state["defect_id"]))

    async def push(self, state: AcceptState) -> None:
        async def act(record: AcceptRecord) -> None:
            # 传的是原来的修复提交:推送被拒绝需要重新放一次时,要用它
            record.pushed_commit = await self._workspace.push_main(state["fix_commit"])

        await self._step(state, 3, act)

    async def build_ota(self, state: AcceptState) -> None:
        async def act(record: AcceptRecord) -> None:
            assert record.pushed_commit
            record.ota = await self._jenkins.build_ota(record.pushed_commit)

        await self._step(state, 4, act)

    async def mark_resolved(self, state: AcceptState) -> None:
        await self._step(state, 5, lambda _: self._feishu.mark_resolved(state["defect_id"]))

    async def comment_version(self, state: AcceptState) -> None:
        async def act(record: AcceptRecord) -> None:
            await self._feishu.comment(state["defect_id"], f"#{record.ota}")

        await self._step(state, 6, act)

    # ------------------------------------------------------------ 每一步共同的流程

    async def _step(self, state: AcceptState, index: int, action: Callable[[AcceptRecord], Awaitable[None]]) -> None:
        """跳过已完成的;检查上次中断的情况;做之前记「开始」,做完记「完成」。"""
        defect_id = state["defect_id"]
        record = self._progress.get(defect_id)
        if record.done > index:
            return  # 上次已经完成,它的产出(提交号、版本号)都在 record 里,后面的步骤会读到
        self._block_if_ambiguous(defect_id, record, index)

        record.running, record.acknowledged = index, False
        self._progress.save(defect_id, record)  # 先记下「开始了」:如果在这里崩溃,重启后就知道这一步可能已经生效

        await action(record)

        record.done, record.running = index + 1, None
        self._progress.save(defect_id, record)

    def _block_if_ambiguous(self, defect_id: str, record: AcceptRecord, index: int) -> None:
        """上次在这一步中断了:能安全重做的放行;否则第一次拦下,用户再点一次才算确认。"""
        if record.running != index or REPEAT_SAFE[index] or record.acknowledged:
            return
        record.acknowledged = True  # 记下「已经提醒过」:用户再点一次接受就视为确认
        self._progress.save(defect_id, record)
        raise AcceptNeedsCheck(
            f"「{ACCEPT_STEPS[index]}」上次执行到一半中断了,无法确认是否已经生效。"
            f"{_WHERE_TO_CHECK[index]},确认后再点「重试接受」。"
        )


def build_accept_graph(nodes: AcceptNodes) -> CompiledStateGraph:
    graph = StateGraph(AcceptState)
    for name in NODE_NAMES:
        graph.add_node(name, getattr(nodes, name))
    graph.add_edge(START, NODE_NAMES[0])
    for current, following in pairwise(NODE_NAMES):
        graph.add_edge(current, following)
    graph.add_edge(NODE_NAMES[-1], END)
    return graph.compile()  # 不用检查点:进度以业务库为准

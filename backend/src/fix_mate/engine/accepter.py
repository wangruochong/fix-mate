"""接受流程的执行器:驱动接受图,把进度汇报出去,失败时说清楚卡在哪一步。"""

from fix_mate.domain.models import Defect
from fix_mate.engine.accept_graph import ACCEPT_STEPS, NODE_NAMES, AcceptNeedsCheck, AcceptNodes, build_accept_graph
from fix_mate.engine.external import AcceptProgressStore, Feishu, Jenkins, Workspace
from fix_mate.engine.ports import AcceptFailed, AcceptProgress, AcceptResult

_STEP_OF_NODE = {name: index for index, name in enumerate(NODE_NAMES)}


class GraphAccepter:
    def __init__(self, *, workspace: Workspace, jenkins: Jenkins, feishu: Feishu, progress: AcceptProgressStore):
        self._progress = progress
        self._graph = build_accept_graph(
            AcceptNodes(workspace=workspace, jenkins=jenkins, feishu=feishu, progress=progress)
        )

    async def accept(self, defect: Defect, on_progress: AcceptProgress) -> AcceptResult:
        """执行接受流程。失败时抛出 AcceptFailed(卡在第几步、原因),缺陷保持待审核,再调用一次会从断点继续。"""
        assert defect.fix is not None
        record = self._progress.get(defect.id)
        on_progress(record.done, record.ota)  # 重试时从已经完成的步骤开始显示

        step = record.done
        try:
            async for event in self._graph.astream(
                {"defect_id": defect.id, "fix_commit": defect.fix.commit}, stream_mode="tasks"
            ):
                if "input" in event:  # 一个步骤开始
                    step = _STEP_OF_NODE[event["name"]]
                elif not event.get("error"):  # 一个步骤完成
                    record = self._progress.get(defect.id)
                    on_progress(record.done, record.ota)
        except AcceptNeedsCheck as e:
            raise AcceptFailed(step, str(e)) from e
        except Exception as e:
            raise AcceptFailed(step, f"{ACCEPT_STEPS[step]}失败:{e}") from e

        record = self._progress.get(defect.id)
        assert record.ota and record.pushed_commit
        return AcceptResult(ota=record.ota, commit=record.pushed_commit)

    async def forget(self, defect_id: str) -> None:
        """接受成功、状态已保存之后,清掉这个缺陷的接受进度。"""
        self._progress.delete(defect_id)

    def unfinished(self) -> dict[str, int]:
        """上次没做完的接受(程序中途退出):缺陷 -> 卡在第几步。"""
        return {
            defect_id: record.running if record.running is not None else record.done
            for defect_id, record in self._progress.unfinished().items()
        }

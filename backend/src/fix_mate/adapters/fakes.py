"""假的外部系统:开发和测试时用,不花钱、不碰网络、行为可预测。

- FakeCodeFixer:在工作目录里写一个小文件来模拟「改代码」,支持中途打断和接着改。
- FakeFeishu / FakeJenkins:只在内存里记录被调用了什么,并能按需注入失败。
"""

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from pathlib import Path

from fix_mate.domain.models import Defect
from fix_mate.engine.external import Assessment, FixReport

#: 假的「改代码」分几段完成。每段之间会检查是否被打断。
_FIX_PARTS = 3


class FakeCodeFixer:
    def __init__(self, *, delay: float = 0.3, speed: float = 1.0):
        self._delay = delay / speed

    async def assess(self, defect: Defect, repo_dir: Path) -> Assessment:
        await asyncio.sleep(self._delay)
        if defect.type == "建议":  # 建议类没有确定的代码修改目标
            return Assessment(False, 70, "这是一条产品体验类建议,没有确定的代码修改目标。")
        return Assessment(True, 90, "问题描述明确,可通过修改代码解决。")

    async def fix(
        self,
        defect: Defect,
        workdir: Path,
        *,
        session_id: str | None,
        on_session: Callable[[str], None],
        interrupt: asyncio.Event,
    ) -> FixReport:
        session_id = session_id or f"fake-{uuid.uuid4().hex[:8]}"
        on_session(session_id)
        # 文件名带上会话号:接着上次的会话改,改的是同一个文件;全新处理一次,就是一个新文件,一定有改动
        target = workdir / "fixmate-demo" / f"{defect.id}-{session_id[-6:]}.md"
        target.parent.mkdir(exist_ok=True)
        # 接着上次改:文件里已经有几行,就说明做完了几段
        done = len(target.read_text().splitlines()) if target.exists() else 0
        for part in range(done, _FIX_PARTS):
            with target.open("a") as f:
                f.write(f"{defect.id} 的修复,第 {part + 1} 段\n")
            last = part == _FIX_PARTS - 1
            if not last and await self._interrupted(interrupt):  # 每做完一段,检查一次是否被要求停下
                return FixReport(summary=[], conclusion=[], session_id=session_id, interrupted=True)
        return FixReport(
            summary=[[f"修改了 fixmate-demo/{defect.id}.md"], ["补充必要的说明"]],
            conclusion=["已分析根因并完成修复,详见 diff。"],
            session_id=session_id,
        )

    async def _interrupted(self, interrupt: asyncio.Event) -> bool:
        """等一小段时间(模拟 AI 工作);期间被打断就立刻返回 True。"""
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(interrupt.wait(), timeout=self._delay)
        return interrupt.is_set()


class FakeFeishu:
    def __init__(self, inbox: list[Defect] | None = None):
        #: 分配给用户的缺陷。测试和开发里往这里加,就等于「飞书上来了新缺陷」
        self.inbox: list[Defect] = list(inbox or [])
        self.resolved: list[str] = []
        self.comments: list[tuple[str, str]] = []
        #: 方法名 -> 要抛出的异常,用来模拟飞书出故障
        self.failures: dict[str, Exception] = {}

    def _maybe_fail(self, method: str) -> None:
        if method in self.failures:
            raise self.failures[method]

    async def fetch_assigned(self) -> list[Defect]:
        self._maybe_fail("fetch_assigned")
        return [d.model_copy(deep=True) for d in self.inbox]

    async def mark_resolved(self, defect_id: str) -> None:
        self._maybe_fail("mark_resolved")
        self.resolved.append(defect_id)

    async def comment(self, defect_id: str, text: str) -> None:
        self._maybe_fail("comment")
        self.comments.append((defect_id, text))


class FakeJenkins:
    def __init__(self, *, delay: float = 0.0):
        self._delay = delay
        self.builds: list[str] = []
        self.failures: dict[str, Exception] = {}

    async def build_ota(self, commit: str) -> str:
        if "build_ota" in self.failures:
            raise self.failures["build_ota"]
        await asyncio.sleep(self._delay)
        self.builds.append(commit)
        return f"3.8.0.{2400 + len(self.builds)}"


class DevFakes:
    """开发模式下手动制造接受流程的故障,用来体验和测试失败后的界面。"""

    def __init__(self, jenkins: FakeJenkins, feishu: FakeFeishu):
        self._jenkins = jenkins
        self._feishu = feishu

    def fail_step(self, step: int | None) -> None:
        """让接受流程的第 step 步(0 起,只支持 4、5、6)失败;传 None 恢复正常。"""
        self._jenkins.failures.clear()
        self._feishu.failures.clear()
        if step is None:
            return
        error = RuntimeError("模拟的故障:服务暂时不可用")
        match step:
            case 4:
                self._jenkins.failures["build_ota"] = error
            case 5:
                self._feishu.failures["mark_resolved"] = error
            case 6:
                self._feishu.failures["comment"] = error
            case _:
                raise ValueError("只支持让第 5、6、7 步(下标 4、5、6)失败")

"""引擎依赖的外部系统。

AI 引擎里的图只通过这里的接口和外界打交道:要改代码找 `CodeFixer`,要动 git 找 `Workspace`,
要读写飞书找 `Feishu`,要打包找 `Jenkins`。好处是:
- 图里没有任何 IO 细节,逐行读图就是读业务流程;
- 测试时换成假实现,不花钱、不碰网络、结果可预测;
- 以后补真实的飞书或 Jenkins,不需要改图。
"""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from fix_mate.domain.models import AcceptRecord, Defect, FixFile, RichText

# ---------------------------------------------------------------- 改代码(Claude Code)


@dataclass(frozen=True)
class Assessment:
    """AI 对「这个缺陷能不能靠改代码解决」的判断。"""

    fixable: bool
    confidence: int
    reason: str


@dataclass(frozen=True)
class FixReport:
    """AI 改完代码后给出的说明。改动本身在工作目录里,不在这里。"""

    summary: list[RichText]
    conclusion: RichText
    #: AI 会话的 id,暂停后用它接着对话
    session_id: str | None = None
    #: 为真表示被打断了,代码改到一半,说明还不完整
    interrupted: bool = False


class CodeFixer(Protocol):
    async def assess(self, defect: Defect, repo_dir: Path) -> Assessment:
        """只读地看代码,判断缺陷能不能靠改代码解决。不修改任何文件。"""

    async def fix(
        self,
        defect: Defect,
        workdir: Path,
        *,
        session_id: str | None,
        on_session: Callable[[str], None],
        interrupt: asyncio.Event,
    ) -> FixReport:
        """在 workdir 里修改代码。

        session_id 不为空表示接着上次的对话继续;拿到新会话的 id 时要立刻调用 on_session,
        这样即使中途被打断也不会丢。interrupt 被设置时,要尽快停下并返回 interrupted=True。
        """


# ---------------------------------------------------------------- git


@dataclass(frozen=True)
class PreparedBranch:
    """为一个缺陷准备好的工作目录和分支。"""

    path: Path
    branch: str
    #: 分支基于哪个 main 提交
    base_commit: str
    #: 恢复时是否已把分支同步到最新 main
    rebased: bool


@dataclass(frozen=True)
class FinishedBranch:
    """AI 改完后整理好的分支:只有一个提交。改动内容用 `Workspace.diff` 另行读取。"""

    commit: str
    base_commit: str


class Workspace(Protocol):
    """FixMate 专用的仓库克隆。所有分支、目录、接受操作都只发生在这里,不碰用户日常的工作区。"""

    # ---- 修复阶段:每个缺陷一个分支和一个临时工作目录
    async def prepare(self, defect_id: str) -> PreparedBranch:
        """创建工作目录和分支;分支已存在(暂停后恢复)就从它重建目录,并同步最新 main。"""

    async def save_progress(self, defect_id: str) -> None:
        """暂停前调用:把未提交的修改存成临时提交,删除工作目录,分支保留。"""

    async def finish(self, defect_id: str, message: str) -> FinishedBranch:
        """AI 改完后调用:压成单个提交,删除工作目录,分支保留。"""

    async def diff(self, base_commit: str, commit: str) -> list[FixFile]:
        """两个提交之间的改动内容。只读,不需要工作目录。"""

    async def discard(self, defect_id: str) -> None:
        """丢弃一个缺陷的分支和目录(没有则忽略)。"""

    # ---- 接受阶段:在专用克隆的主工作区里,把分支上的提交放进 main
    async def sync_main(self) -> None:
        """切到 main,并与远端对齐。"""

    async def cherry_pick(self, commit: str) -> str:
        """把提交放进 main,返回 main 当前的提交号。冲突时撤销并抛出 ConflictError。

        可以安全地重复调用:main 里已经有这个修复了就什么都不做。
        """

    async def push_main(self, commit: str) -> str:
        """推送 main。commit 是**原来的修复提交**(不是 main 上新生成的那个)。

        被拒绝时(远端有新提交)重新对齐后,再把这个修复放一次并重试一次;绝不强推。返回最终提交号。
        """

    async def delete_branch(self, defect_id: str) -> None:
        """接受完成后删除该缺陷的临时分支。分支已不存在时忽略。"""


class SessionStore(Protocol):
    """记住每个缺陷的 AI 会话号。放在业务库里,而不是图的检查点里:

    改代码的节点被打断时,它还没有「完成」,图的状态不会保存,但会话号必须保住,恢复时才能接着对话。
    """

    def get(self, defect_id: str) -> str | None: ...

    def save(self, defect_id: str, session_id: str) -> None: ...


class AcceptProgressStore(Protocol):
    """接受流程的进度存储。放在业务库里,重启后以它为准。"""

    def get(self, defect_id: str) -> AcceptRecord: ...

    def save(self, defect_id: str, record: AcceptRecord) -> None: ...

    def delete(self, defect_id: str) -> None: ...

    def unfinished(self) -> dict[str, AcceptRecord]: ...


# ---------------------------------------------------------------- 飞书和 Jenkins


class Feishu(Protocol):
    async def fetch_assigned(self) -> list[Defect]:
        """拉取分配给当前用户的、还没有解决的缺陷。"""

    async def mark_resolved(self, defect_id: str) -> None:
        """把缺陷标记为已解决。"""

    async def comment(self, defect_id: str, text: str) -> None:
        """在缺陷下发表评论。"""


class Jenkins(Protocol):
    async def build_ota(self, commit: str) -> str:
        """触发 OTA 打包并等它完成,返回版本号。"""

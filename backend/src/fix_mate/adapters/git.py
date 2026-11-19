"""真实的 git 实现。所有操作都发生在 FixMate 专用的仓库克隆里,不碰用户日常的工作区。

目录约定:
    repo/                      专用克隆,主工作区一直停在 main,接受流程在这里操作
    worktrees_dir/<缺陷编号>/   每个缺陷处理期间的临时工作目录,分支是 fixmate/<缺陷编号>

这里每个注意点都来自实际验证(见设计文档第 10 节的「已验证的技术结论」):
- 同一分支不能在两个目录检出;有未提交修改的目录不能直接删,所以删目录前先把修改存成临时提交。
- 一个缺陷最终只留一个提交,cherry-pick 才干净。
- cherry-pick 或变基冲突时必须 `--abort`,不能在仓库里留下半成品状态。
- 推送被拒绝时只重来一次,绝不强推。
"""

import asyncio
import os
import re
from pathlib import Path

from fix_mate.domain.models import FixFile
from fix_mate.engine.diffs import parse_diff
from fix_mate.engine.external import FinishedBranch, PreparedBranch

#: 缺陷编号只允许字母、数字和连字符。它会被拼进分支名和目录名,必须严格校验,防止路径穿越或参数注入
_DEFECT_ID = re.compile(r"[A-Za-z]+-\d+")


class GitError(Exception):
    """git 命令失败。"""


class ConflictError(GitError):
    """cherry-pick 或变基遇到冲突。仓库已经恢复到干净状态。"""


class NothingChanged(GitError):
    """AI 处理完之后,工作目录里没有任何修改。"""


class PushRejected(GitError):
    """远端有新提交,推送被拒绝。"""


class GitWorkspace:
    def __init__(
        self,
        repo: Path,
        worktrees_dir: Path,
        *,
        main_branch: str = "main",
        remote: str = "origin",
        env: dict[str, str] | None = None,
    ):
        self._repo = repo
        self._worktrees_dir = worktrees_dir
        self._main = main_branch
        self._remote = remote
        self._env = {**os.environ, "GIT_TERMINAL_PROMPT": "0", **(env or {})}
        # 对同一个仓库的 git 操作排队执行,避免两个操作同时抢 .git 里的锁文件
        self._lock = asyncio.Lock()

    # ---------------------------------------------------------------- 修复阶段

    async def prepare(self, defect_id: str) -> PreparedBranch:
        branch, path = self._names(defect_id)
        async with self._lock:
            await self._git("fetch", self._remote)
            await self._git("worktree", "prune")  # 清掉上次异常退出留下的失效记录
            origin_main = await self._rev(f"{self._remote}/{self._main}")
            if path.exists():
                # 上一次已经建好了目录,只是还没来得及记录就中断了。沿用它,不要重复创建
                return PreparedBranch(path=path, branch=branch, base_commit=origin_main, rebased=False)
            if not await self._branch_exists(branch):
                await self._git("worktree", "add", "-b", branch, str(path), origin_main)
                return PreparedBranch(path=path, branch=branch, base_commit=origin_main, rebased=False)

            # 暂停后恢复:分支还在,从它重建目录
            await self._git("worktree", "add", str(path), branch)
            try:
                rebased = await self._rebase_if_main_moved(path, origin_main)
            except ConflictError:
                # 变基已经撤销,但目录还占着分支:一并删掉,只保留分支,否则下次无法再准备这个缺陷
                await self._git("worktree", "remove", "--force", str(path))
                raise
            return PreparedBranch(path=path, branch=branch, base_commit=origin_main, rebased=rebased)

    async def save_progress(self, defect_id: str) -> None:
        _, path = self._names(defect_id)
        async with self._lock:
            if not path.exists():
                return
            await self._commit_everything(path, f"wip: {defect_id}")
            await self._git("worktree", "remove", str(path))

    async def finish(self, defect_id: str, message: str) -> FinishedBranch:
        _, path = self._names(defect_id)
        async with self._lock:
            await self._commit_everything(path, f"wip: {defect_id}")
            base = (await self._git("merge-base", "HEAD", f"{self._remote}/{self._main}", cwd=path)).strip()
            if base == await self._rev("HEAD", cwd=path):
                # 相对 main 一个提交都没有:AI 什么都没改。提示清楚,不要让用户去看 git 的内部报错
                raise NothingChanged("AI 处理完了,但没有产生任何代码修改,没有可审核的内容。")
            # 把期间所有的临时提交压成一个:软重置回基线,再整体提交一次
            await self._git("reset", "--soft", base, cwd=path)
            await self._git(*self._commit_args(message), cwd=path)
            commit = await self._rev("HEAD", cwd=path)
            await self._git("worktree", "remove", str(path))
            return FinishedBranch(commit=commit, base_commit=base)

    async def diff(self, base_commit: str, commit: str) -> list[FixFile]:
        return parse_diff(await self._git("diff", f"{base_commit}..{commit}"))

    async def discard(self, defect_id: str) -> None:
        branch, path = self._names(defect_id)
        async with self._lock:
            if path.exists():
                await self._git("worktree", "remove", "--force", str(path))
            await self._git("worktree", "prune")
            if await self._branch_exists(branch):
                await self._git("branch", "-D", branch)

    # ---------------------------------------------------------------- 接受阶段(在专用克隆的主工作区)

    async def sync_main(self) -> None:
        async with self._lock:
            await self._git("fetch", self._remote)
            await self._git("checkout", self._main)
            await self._git("merge", "--ff-only", f"{self._remote}/{self._main}")

    async def cherry_pick(self, commit: str) -> str:
        async with self._lock:
            return await self._cherry_pick(commit)

    async def push_main(self, commit: str) -> str:
        async with self._lock:
            try:
                await self._push()
                return await self._rev("HEAD")
            except PushRejected:
                # 远端在这期间有了新提交。把本地 main 对齐到远端,再把我们的提交放一次,重试一次。
                # 不强推:强推会覆盖别人的提交。
                await self._git("fetch", self._remote)
                await self._git("reset", "--hard", f"{self._remote}/{self._main}")
                await self._cherry_pick(commit)
                await self._push()
                return await self._rev("HEAD")

    async def delete_branch(self, defect_id: str) -> None:
        """接受完成后删除该缺陷的临时分支。分支已不存在时忽略。"""
        branch, _ = self._names(defect_id)
        async with self._lock:
            if await self._branch_exists(branch):
                await self._git("branch", "-D", branch)

    # ---------------------------------------------------------------- 内部:git 小操作

    async def _already_applied(self, commit: str) -> bool:
        """main 里是不是已经有这个修复了。有两种情况:原提交本身就在 main 的历史里,
        或者 main 里有内容等价的提交(git cherry 把等价的标成 "-",还没放进去的标成 "+")。"""
        if await self._succeeded("merge-base", "--is-ancestor", commit, "HEAD"):
            return True
        marks = await self._git("cherry", "HEAD", commit, f"{commit}~1")
        return any(line.startswith("- ") for line in marks.splitlines())

    async def _cherry_pick(self, commit: str) -> str:
        if await self._already_applied(commit):
            return await self._rev("HEAD")
        try:
            await self._git("cherry-pick", commit)
        except GitError as e:
            await self._git("cherry-pick", "--abort", check=False)  # 无论如何回到干净状态
            raise ConflictError(f"提交 {commit[:7]} 与 {self._main} 上的最新代码冲突:{e}") from e
        return await self._rev("HEAD")

    async def _push(self) -> None:
        try:
            await self._git("push", self._remote, self._main)
        except GitError as e:
            if "rejected" in str(e) or "non-fast-forward" in str(e):
                raise PushRejected(str(e)) from e
            raise

    async def _rebase_if_main_moved(self, path: Path, origin_main: str) -> bool:
        """分支基于的 main 已经过时,就变基到最新 main。冲突时撤销,交给调用方处理。"""
        base = (await self._git("merge-base", "HEAD", origin_main, cwd=path)).strip()
        if base == origin_main:
            return False
        try:
            await self._git("rebase", origin_main, cwd=path)
        except GitError as e:
            await self._git("rebase", "--abort", cwd=path, check=False)
            raise ConflictError(f"同步最新 {self._main} 时冲突:{e}") from e
        return True

    async def _commit_everything(self, path: Path, message: str) -> None:
        """把工作目录里所有修改(包括新文件)提交;没有修改就什么都不做。"""
        await self._git("add", "-A", cwd=path)
        if (await self._git("status", "--porcelain", cwd=path)).strip():
            await self._git(*self._commit_args(message), cwd=path)

    @staticmethod
    def _commit_args(message: str) -> list[str]:
        # --no-verify:这些是 AI 的中间提交和整理后的提交,用户审核的是最终 diff;
        # 专用克隆里通常也没有项目的 hook 所需环境。不关闭签名,避免弹出密码输入而卡住。
        return ["-c", "commit.gpgsign=false", "commit", "--no-verify", "-m", message]

    async def _branch_exists(self, branch: str) -> bool:
        out = await self._git("branch", "--list", branch)
        return bool(out.strip())

    async def _rev(self, ref: str, cwd: Path | None = None) -> str:
        return (await self._git("rev-parse", ref, cwd=cwd)).strip()

    def _names(self, defect_id: str) -> tuple[str, Path]:
        if not _DEFECT_ID.fullmatch(defect_id):
            raise ValueError(f"不合法的缺陷编号:{defect_id!r}")
        return f"fixmate/{defect_id}", self._worktrees_dir / defect_id

    async def _succeeded(self, *args: str) -> bool:
        """命令是否成功(退出码为 0),用于「是或否」的判断。"""
        proc = await asyncio.create_subprocess_exec(
            "git", *args, cwd=self._repo, env=self._env, stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
        )  # fmt: skip
        return await proc.wait() == 0

    async def _git(self, *args: str, cwd: Path | None = None, check: bool = True) -> str:
        """运行一条 git 命令,返回标准输出。失败时抛出带原因的 GitError。"""
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            cwd=cwd or self._repo,
            env=self._env,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        out, err = await proc.communicate()
        if check and proc.returncode != 0:
            raise GitError(f"git {' '.join(args)} 失败:{err.decode(errors='replace').strip()}")
        return out.decode(errors="replace")

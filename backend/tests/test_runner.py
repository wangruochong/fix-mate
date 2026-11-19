"""运行器和修复图的测试:真实的 git 仓库 + 假的改代码,验证完整流程、暂停恢复、崩溃重启。"""

import asyncio

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from fix_mate.adapters.fakes import FakeCodeFixer
from fix_mate.engine.checkpoints import open_checkpointer
from fix_mate.engine.ports import Failed, Fixed, RunRef, Skipped
from fix_mate.engine.runner import GraphRunner
from tests.conftest import make_defect
from tests.git_helpers import Repos, run


class MemorySessions:
    def __init__(self):
        self.data: dict[str, str] = {}

    def get(self, defect_id):
        return self.data.get(defect_id)

    def save(self, defect_id, session_id):
        self.data[defect_id] = session_id


class Recorder:
    """记录运行器汇报的所有事。"""

    def __init__(self):
        self.events: list[tuple] = []
        self.result = None
        self.done = asyncio.Event()

    def step_started(self, run, step):
        self.events.append(("step", step))

    def rebased(self, run):
        self.events.append(("rebased",))

    def finished(self, run, result):
        self.result = result
        self.done.set()

    @property
    def steps(self):
        return [e[1] for e in self.events if e[0] == "step"]

    async def wait_finished(self):
        await asyncio.wait_for(self.done.wait(), 10)
        return self.result

    async def wait_step(self, step):
        for _ in range(500):
            if step in self.steps:
                return
            await asyncio.sleep(0.01)
        raise AssertionError(f"等不到第 {step} 步,实际 {self.steps}")


DEFECTS = {
    "BUG-1": make_defect("BUG-1", title="登录页无响应"),
    "SUG-1": make_defect("SUG-1", type="建议", title="希望改文案"),
}


@pytest.fixture
def repos(tmp_path):
    return Repos(tmp_path)


def make_runner(repos, checkpointer=None, sessions=None, fixer=None, **kw):
    return GraphRunner(
        fixer=fixer or FakeCodeFixer(delay=0.03),
        workspace=repos.workspace,
        sessions=sessions or MemorySessions(),
        checkpointer=checkpointer or InMemorySaver(),
        load_defect=lambda defect_id: DEFECTS[defect_id],
        repo_dir=repos.clone,
        **kw,
    )


def demo_name(sessions, defect_id="BUG-1"):
    """假改代码为这个缺陷写的文件名(随 AI 会话变化)。"""
    return f"fixmate-demo/{defect_id}-{sessions.get(defect_id)[-6:]}.md"


def worktree_dir(repos, defect_id="BUG-1"):
    return repos.clone.parent / "worktrees" / defect_id


async def test_a_fixable_defect_runs_through_all_steps_and_ends_with_a_single_commit(repos):
    sessions = MemorySessions()
    rec, runner = Recorder(), make_runner(repos, sessions=sessions)
    runner.start(RunRef("BUG-1", 1), DEFECTS["BUG-1"], False, rec)
    result = await rec.wait_finished()

    assert isinstance(result, Fixed)
    assert rec.steps == [0, 1, 2, 2]  # 判断、建分支、改代码、整理(界面上仍是改代码)
    fix = result.fix
    assert fix.branch == "fixmate/BUG-1" and fix.confidence == 90
    assert [f.name for f in fix.files] == [demo_name(sessions)] and fix.files[0].additions == 3
    assert run(repos.clone, "rev-list", "--count", f"{result.base_commit}..{fix.commit}") == "1"
    assert run(repos.clone, "log", "-1", "--format=%s", fix.commit) == "fix: BUG-1 登录页无响应"
    assert not worktree_dir(repos).exists()  # 工作目录已删除,分支保留
    assert run(repos.clone, "branch", "--list", "fixmate/BUG-1")


async def test_an_unfixable_defect_is_skipped_without_creating_a_branch(repos):
    rec, runner = Recorder(), make_runner(repos)
    runner.start(RunRef("SUG-1", 1), DEFECTS["SUG-1"], False, rec)
    result = await rec.wait_finished()

    assert isinstance(result, Skipped) and "已自动跳过" in result.reason
    assert rec.steps == [0]
    assert run(repos.clone, "branch", "--list", "fixmate/*") == ""


async def test_pausing_during_write_code_saves_progress_and_resuming_finishes_the_work(repos):
    sessions, checkpointer = MemorySessions(), InMemorySaver()
    runner = make_runner(repos, checkpointer, sessions)
    first = Recorder()
    runner.start(RunRef("BUG-1", 1), DEFECTS["BUG-1"], False, first)
    await first.wait_step(2)
    await runner.pause(RunRef("BUG-1", 1))

    assert first.result is None  # 被暂停的不会汇报「结束」
    assert not worktree_dir(repos).exists()  # 目录已删除
    assert "wip: BUG-1" in run(repos.clone, "log", "fixmate/BUG-1", "--format=%s")  # 进度存成了临时提交
    session_before = sessions.get("BUG-1")
    assert session_before

    second = Recorder()
    runner.start(RunRef("BUG-1", 2), DEFECTS["BUG-1"], True, second)
    result = await second.wait_finished()
    assert isinstance(result, Fixed)
    assert sessions.get("BUG-1") == session_before  # 接着同一个 AI 会话
    # 暂停前后的改动合在了一起,没有重复,而且只有一个提交
    assert result.fix.files[0].additions == 3
    assert run(repos.clone, "rev-list", "--count", f"{result.base_commit}..{result.fix.commit}") == "1"
    assert second.steps[0] == 1 and 0 not in second.steps  # 恢复时重新准备工作目录,但不会让 AI 重新判断一次


async def test_pausing_before_the_workspace_exists_is_harmless(repos):
    runner, rec = make_runner(repos), Recorder()
    runner.start(RunRef("BUG-1", 1), DEFECTS["BUG-1"], False, rec)
    await runner.pause(RunRef("BUG-1", 1))  # 此时多半还在判断阶段
    assert rec.result is None and not worktree_dir(repos).exists()

    again = Recorder()
    runner.start(RunRef("BUG-1", 2), DEFECTS["BUG-1"], True, again)
    assert isinstance(await again.wait_finished(), Fixed)


async def test_pausing_a_finished_run_does_nothing(repos):
    runner, rec = make_runner(repos), Recorder()
    ref = RunRef("BUG-1", 1)
    runner.start(ref, DEFECTS["BUG-1"], False, rec)
    await rec.wait_finished()
    await runner.pause(ref)  # 已经结束,不应报错也不应卡住


async def test_resuming_after_a_crash_continues_from_the_checkpoint(repos, tmp_path):
    """进程「崩溃」(强制停掉),换全新的检查点连接和运行器,仍能从上次的进度继续。"""
    db = str(tmp_path / "checkpoints.db")
    sessions = MemorySessions()

    async with open_checkpointer(db) as saver:
        runner, rec = make_runner(repos, saver, sessions), Recorder()
        runner.start(RunRef("BUG-1", 1), DEFECTS["BUG-1"], False, rec)
        await rec.wait_step(2)
        await runner.shutdown()  # 相当于进程被终止

    async with open_checkpointer(db) as saver:
        runner, rec = make_runner(repos, saver, sessions), Recorder()
        runner.start(RunRef("BUG-1", 2), DEFECTS["BUG-1"], True, rec)
        result = await rec.wait_finished()
    assert isinstance(result, Fixed) and result.fix.files[0].additions == 3


async def test_resuming_after_main_moved_reports_the_rebase(repos):
    runner, first = make_runner(repos), Recorder()
    runner.start(RunRef("BUG-1", 1), DEFECTS["BUG-1"], False, first)
    await first.wait_step(2)
    await runner.pause(RunRef("BUG-1", 1))
    repos.colleague_commit("b.txt", "别人的改动\n", "colleague")  # 暂停期间 main 前进了

    second = Recorder()
    runner.start(RunRef("BUG-1", 2), DEFECTS["BUG-1"], True, second)
    result = await second.wait_finished()
    assert ("rebased",) in second.events
    assert isinstance(result, Fixed) and result.base_commit == repos.origin_main()


async def test_a_failure_is_reported_and_the_work_so_far_is_kept(repos):
    class Boom(FakeCodeFixer):
        async def fix(self, defect, workdir, **kw):
            (workdir / "half.txt").write_text("改了一半\n")
            raise RuntimeError("AI 服务不可用")

    runner, rec = make_runner(repos, fixer=Boom(delay=0)), Recorder()
    runner.start(RunRef("BUG-1", 1), DEFECTS["BUG-1"], False, rec)
    result = await rec.wait_finished()

    assert isinstance(result, Failed) and "AI 服务不可用" in result.message
    assert not worktree_dir(repos).exists()
    assert "half.txt" in run(repos.clone, "show", "--stat", "--format=", "fixmate/BUG-1")  # 改了一半的成果没丢


async def test_a_rebase_conflict_is_reported_as_a_failure(repos):
    sessions = MemorySessions()
    runner, first = make_runner(repos, sessions=sessions), Recorder()
    runner.start(RunRef("BUG-1", 1), DEFECTS["BUG-1"], False, first)
    await first.wait_step(2)
    await runner.pause(RunRef("BUG-1", 1))
    # 暂停前 FakeCodeFixer 只新增了 fixmate-demo 下的文件;让同事也在同一路径加一个内容不同的同名文件
    repos.colleague_commit(demo_name(sessions), "别人写的\n", "conflict")

    second = Recorder()
    runner.start(RunRef("BUG-1", 2), DEFECTS["BUG-1"], True, second)
    result = await second.wait_finished()
    assert isinstance(result, Failed) and "冲突" in result.message


async def test_starting_fresh_after_a_completed_run_clears_the_old_checkpoint(repos):
    checkpointer = InMemorySaver()
    runner, first = make_runner(repos, checkpointer), Recorder()
    runner.start(RunRef("BUG-1", 1), DEFECTS["BUG-1"], False, first)
    await first.wait_finished()

    second = Recorder()
    runner.start(RunRef("BUG-1", 2), DEFECTS["BUG-1"], False, second)  # 不是恢复,而是重新开始
    assert isinstance(await second.wait_finished(), Fixed)
    assert second.steps[0] == 0  # 从第一步重新开始,没有被旧检查点带偏


async def test_resuming_without_a_checkpoint_starts_from_the_beginning(repos):
    """演示数据里「已暂停」的缺陷没有检查点,要求恢复时应当从头做,而不是报错。"""
    runner, rec = make_runner(repos), Recorder()
    runner.start(RunRef("BUG-1", 1), DEFECTS["BUG-1"], True, rec)
    assert isinstance(await rec.wait_finished(), Fixed)
    assert rec.steps[0] == 0


async def test_a_run_that_ignores_the_pause_signal_is_cancelled_as_a_last_resort(repos):
    class Stubborn(FakeCodeFixer):
        async def fix(self, defect, workdir, **kw):
            (workdir / "partial.txt").write_text("没存盘的修改\n")
            await asyncio.sleep(60)  # 不理会暂停信号

    runner, rec = make_runner(repos, fixer=Stubborn(delay=0), pause_timeout=0.2), Recorder()
    runner.start(RunRef("BUG-1", 1), DEFECTS["BUG-1"], False, rec)
    await rec.wait_step(2)
    await asyncio.wait_for(runner.pause(RunRef("BUG-1", 1)), 5)  # 超时后强制取消,不会一直卡住

    assert rec.result is None and not worktree_dir(repos).exists()
    assert "partial.txt" in run(repos.clone, "show", "--stat", "--format=", "fixmate/BUG-1")  # 强制取消时也保存了进度


async def test_an_ai_that_changed_nothing_is_reported_clearly(repos):
    class Lazy(FakeCodeFixer):
        async def fix(self, defect, workdir, **kw):
            from fix_mate.engine.external import FixReport

            return FixReport(summary=[], conclusion=[], session_id="s")  # 什么都没改

    runner, rec = make_runner(repos, fixer=Lazy(delay=0)), Recorder()
    runner.start(RunRef("BUG-1", 1), DEFECTS["BUG-1"], False, rec)
    result = await rec.wait_finished()
    assert isinstance(result, Failed) and "没有产生任何代码修改" in result.message

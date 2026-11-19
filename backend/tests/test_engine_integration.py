"""集成测试:调度器 + 命令 + 真实的 AI 引擎(LangGraph)+ 真实的 git 仓库 + 假的改代码。

验证整条链路:从「用户点开始」到「缺陷进入待审核」,以及插队、暂停、崩溃后的恢复。
"""

import asyncio
from dataclasses import dataclass

import pytest

from fix_mate.adapters.fakes import FakeCodeFixer
from fix_mate.engine.checkpoints import open_checkpointer
from fix_mate.engine.runner import GraphRunner
from fix_mate.engine.stub import StubExecutor
from fix_mate.services.commands import Commands
from fix_mate.services.events import EventBus
from fix_mate.services.notifier import Notifier
from fix_mate.services.scheduler import Scheduler
from fix_mate.store.db import open_database
from fix_mate.store.repository import Repository, RepositorySessions
from tests.conftest import NOW, make_defect, make_list
from tests.git_helpers import Repos, run


@dataclass
class Real:
    repos: Repos
    repo: Repository
    commands: Commands
    scheduler: Scheduler
    runner: GraphRunner
    saver: object

    def defect(self, defect_id):
        return self.repo.get_defect(defect_id)

    async def wait_state(self, defect_id, state, timeout=15.0):
        deadline = asyncio.get_running_loop().time() + timeout
        while self.defect(defect_id).state != state:
            assert asyncio.get_running_loop().time() < deadline, (
                f"{defect_id} 一直没有变成 {state},现在是 {self.defect(defect_id).state}"
            )
            await asyncio.sleep(0.01)
        await self.scheduler.drain()

    def worktree(self, defect_id):
        return self.repos.clone.parent / "worktrees" / defect_id

    def branch_log(self, defect_id):
        return run(self.repos.clone, "log", f"fixmate/{defect_id}", "--format=%s").splitlines()


def build(repos, repo, saver) -> tuple[GraphRunner, Scheduler, Commands]:
    bus = EventBus(coalesce_seconds=0)
    notifier = Notifier(repo, bus, lambda: NOW)
    runner = GraphRunner(
        fixer=FakeCodeFixer(delay=0.03),
        workspace=repos.workspace,
        sessions=RepositorySessions(repo),
        checkpointer=saver,
        load_defect=lambda defect_id: repo.get_defect(defect_id),
        repo_dir=repos.clone,
    )
    scheduler = Scheduler(repo, runner, bus, notifier, lambda: NOW)
    stub = StubExecutor(interval=None)
    return runner, scheduler, Commands(repo, scheduler, stub, stub, bus, notifier, lambda: NOW)


@pytest.fixture
async def real(tmp_path):
    repos = Repos(tmp_path)
    repo = Repository(open_database(":memory:"))
    for d in ("BUG-2", "BUG-3", "BUG-4"):
        repo.save_defect(make_defect(d, title=f"缺陷 {d}"))
    repo.save_list(make_list("URGENT", [], urgent=True, seq=0))
    repo.save_list(make_list("L1", ["BUG-2", "BUG-3"], on=False, seq=1))
    async with open_checkpointer(":memory:") as saver:
        runner, scheduler, commands = build(repos, repo, saver)
        await scheduler.start()
        yield Real(repos, repo, commands, scheduler, runner, saver)
        await commands.shutdown()
        await scheduler.stop()


async def test_a_list_is_processed_for_real_defect_by_defect(real):
    await real.commands.start_list("L1")
    await real.wait_state("BUG-2", "review")
    fix = real.defect("BUG-2").fix
    assert fix.branch == "fixmate/BUG-2" and fix.files[0].name.startswith("fixmate-demo/BUG-2-")
    assert not real.worktree("BUG-2").exists()  # 目录已删除,分支保留
    assert real.branch_log("BUG-2")[0] == "fix: BUG-2 缺陷 BUG-2"

    await real.wait_state("BUG-3", "review")  # 接着处理清单里的下一个
    assert real.defect("BUG-3").fix.branch == "fixmate/BUG-3"


async def test_an_urgent_defect_pauses_the_running_one_for_real_and_it_resumes_afterwards(real):
    await real.commands.start_list("L1")
    for _ in range(500):  # 等 BUG-2 真的写出了第一段修改
        if list((real.worktree("BUG-2") / "fixmate-demo").glob("BUG-2-*.md")):
            break
        await asyncio.sleep(0.01)

    await real.commands.set_urgent("BUG-4", "front")
    paused = real.defect("BUG-2")
    assert paused.state == "paused" and paused.pause.cause == "preempted"
    assert not real.worktree("BUG-2").exists()  # 暂停时目录被删除
    assert "wip: BUG-2" in real.branch_log("BUG-2")  # 做到一半的修改存成了临时提交

    await real.wait_state("BUG-4", "review")  # 紧急的先做完
    await real.wait_state("BUG-2", "review")  # 然后自动恢复被打断的
    fix = real.defect("BUG-2").fix
    assert fix.files[0].additions == 3  # 暂停前后的改动合在一起,没有重复
    assert run(real.repos.clone, "rev-list", "--count", f"origin/main..{fix.commit}") == "1"  # 最终只有一个提交


async def test_rejecting_with_discard_removes_the_branch(real):
    await real.commands.start_list("L1")
    await real.wait_state("BUG-2", "review")
    assert run(real.repos.clone, "branch", "--list", "fixmate/BUG-2")
    await real.commands.reject("BUG-2", False, "不要了")
    assert run(real.repos.clone, "branch", "--list", "fixmate/BUG-2") == ""


async def test_rejecting_with_keep_changes_keeps_the_branch(real):
    await real.commands.start_list("L1")
    await real.wait_state("BUG-2", "review")
    await real.commands.reject("BUG-2", True, "保留")
    assert run(real.repos.clone, "branch", "--list", "fixmate/BUG-2")


async def test_after_a_crash_the_interrupted_defect_continues_from_its_saved_progress(real):
    await real.commands.start_list("L1")
    for _ in range(500):
        if real.worktree("BUG-2").exists():
            break
        await asyncio.sleep(0.01)
    assert real.defect("BUG-2").state == "analyzing"

    # 「崩溃」:停掉旧的调度器和运行器,数据库里仍然记着「处理中」
    await real.commands.shutdown()
    await real.scheduler.stop()
    assert real.defect("BUG-2").state in ("analyzing", "paused")

    # 「重启」:全新的调度器和运行器,共用同样的数据库和检查点
    runner, scheduler, commands = build(real.repos, real.repo, real.saver)
    await scheduler.start()
    try:
        fresh = Real(real.repos, real.repo, commands, scheduler, runner, real.saver)
        await fresh.wait_state("BUG-2", "review")
        assert fresh.defect("BUG-2").fix.files[0].additions == 3
    finally:
        await commands.shutdown()
        await scheduler.stop()


async def test_a_failure_pauses_the_defect_with_the_reason_and_moves_on(real):
    class Boom(FakeCodeFixer):
        async def assess(self, defect, repo_dir):
            if defect.id == "BUG-2":
                raise RuntimeError("AI 服务不可用")
            return await super().assess(defect, repo_dir)

    real.runner._fixer = Boom(delay=0.01)
    await real.commands.start_list("L1")
    await real.wait_state("BUG-2", "paused")
    d = real.defect("BUG-2")
    assert d.pause.cause == "user" and "AI 服务不可用" in d.pause.note
    await real.wait_state("BUG-3", "review")  # 出错的不影响清单里其它缺陷

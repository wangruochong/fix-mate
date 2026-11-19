"""接受流程的测试:真实的 git + 假的 Jenkins 和飞书。重点是失败、重试和「不能做两次」的步骤。"""

import pytest

from fix_mate.adapters.fakes import FakeFeishu, FakeJenkins
from fix_mate.domain.models import AcceptRecord
from fix_mate.engine.accept_graph import ACCEPT_STEPS
from fix_mate.engine.accepter import GraphAccepter
from fix_mate.engine.ports import AcceptFailed
from fix_mate.store.db import open_database
from fix_mate.store.repository import Repository, RepositoryAcceptProgress
from tests.conftest import make_defect
from tests.git_helpers import Repos, run


class Setup:
    def __init__(self, repos: Repos, repo: Repository):
        self.repos = repos
        self.jenkins = FakeJenkins()
        self.feishu = FakeFeishu()
        self.progress = RepositoryAcceptProgress(repo)
        self.accepter = GraphAccepter(
            workspace=repos.workspace, jenkins=self.jenkins, feishu=self.feishu, progress=self.progress
        )
        self.events: list[tuple[int, str | None]] = []
        self.defect = None

    async def prepare_fix(self):
        """先让引擎产出一个待审核的修复(分支上有一个提交)。"""
        prepared = await self.repos.workspace.prepare("BUG-1")
        (prepared.path / "a.txt").write_text("line1\nFIXED\nline3\n")
        done = await self.repos.workspace.finish("BUG-1", "fix: BUG-1")
        from fix_mate.domain.models import Fix

        fix = Fix(
            confidence=90,
            branch="fixmate/BUG-1",
            commit=done.commit,
            judge="",
            summary=[],
            conclusion=[],
            files=[],
            conflicts=[],
        )
        self.defect = make_defect("BUG-1", "review", fix=fix)

    async def accept(self):
        return await self.accepter.accept(self.defect, lambda step, ota: self.events.append((step, ota)))


@pytest.fixture
async def acc(tmp_path):
    s = Setup(Repos(tmp_path), Repository(open_database(":memory:")))
    await s.prepare_fix()
    return s


async def test_a_successful_accept_runs_seven_steps_in_order(acc):
    result = await acc.accept()

    assert acc.repos.origin_file("a.txt") == "line1\nFIXED\nline3"  # 修复已在远端 main
    assert result.commit == acc.repos.origin_main() and result.ota == "3.8.0.2401"
    assert run(acc.repos.clone, "branch", "--list", "fixmate/BUG-1") == ""  # 临时分支已删除
    assert acc.jenkins.builds == [result.commit]  # 对最终推送的提交打包
    assert acc.feishu.resolved == ["BUG-1"] and acc.feishu.comments == [("BUG-1", "#3.8.0.2401")]
    assert [e[0] for e in acc.events] == [0, 1, 2, 3, 4, 5, 6, 7]  # 进度逐步汇报
    assert acc.events[-1][1] == "3.8.0.2401"


@pytest.mark.parametrize("failing", ["fetch", "push", "build_ota", "mark_resolved", "comment"])
async def test_a_failure_reports_the_step_and_a_retry_continues_without_redoing_finished_steps(acc, failing):
    """每个会失败的外部步骤:失败后说明卡在哪一步,重试只做剩下的,不重复 push 和打包。"""
    boom = RuntimeError(f"{failing} 出错了")
    target = {
        "fetch": (acc.repos.workspace, "sync_main"),  # 第 1 步
        "push": (acc.repos.workspace, "push_main"),  # 第 4 步
        "build_ota": (acc.jenkins, None),  # 第 5 步
        "mark_resolved": (acc.feishu, None),  # 第 6 步
        "comment": (acc.feishu, None),  # 第 7 步
    }[failing]
    expected_step = {"fetch": 0, "push": 3, "build_ota": 4, "mark_resolved": 5, "comment": 6}[failing]
    restore = None
    if target[1]:  # git 的方法:临时换成会失败的
        original = getattr(target[0], target[1])

        async def fail(*a, **k):
            raise boom

        setattr(target[0], target[1], fail)
        restore = lambda: setattr(target[0], target[1], original)  # noqa: E731
    else:
        target[0].failures[
            {"build_ota": "build_ota", "mark_resolved": "mark_resolved", "comment": "comment"}[failing]
        ] = boom

    with pytest.raises(AcceptFailed) as e:
        await acc.accept()
    assert e.value.step == expected_step
    assert failing in e.value.message or ACCEPT_STEPS[expected_step] in e.value.message
    assert acc.progress.get("BUG-1").done == expected_step  # 之前的步骤都已落盘

    # 故障排除后重试
    if restore:
        restore()
    else:
        target[0].failures.clear()
    if failing in ("build_ota", "comment"):  # 这两步不能安全重做:第一次重试会被拦下,要用户确认
        with pytest.raises(AcceptFailed, match="无法确认"):
            await acc.accept()
    result = await acc.accept()

    assert result.ota and acc.jenkins.builds == [result.commit]  # 无论哪一步失败,只打了一次包
    assert acc.feishu.resolved == ["BUG-1"]
    assert acc.repos.origin_file("a.txt") == "line1\nFIXED\nline3"
    # push 之后失败的,重试没有再放一遍修复(main 上只有一个修复提交)
    assert run(acc.repos.clone, "log", "origin/main", "--format=%s").splitlines().count("fix: BUG-1") == 1


async def test_a_step_that_must_not_be_repeated_needs_confirmation_after_an_interruption(acc):
    """打 OTA 包到一半中断(比如进程崩溃),不知道 Jenkins 有没有收到请求。不能自动重试,以免打两个包。"""
    acc.progress.save("BUG-1", AcceptRecord(done=4, running=4, pushed_commit="abc1234"))  # 模拟崩溃留下的现场

    with pytest.raises(AcceptFailed, match="请先到 Jenkins 确认") as first:
        await acc.accept()
    assert first.value.step == 4 and acc.jenkins.builds == []  # 没有打包

    result = await acc.accept()  # 用户确认后再点一次:才继续
    assert acc.jenkins.builds == ["abc1234"] and result.ota == "3.8.0.2401"


async def test_a_step_that_is_safe_to_repeat_continues_without_asking(acc):
    acc.progress.save("BUG-1", AcceptRecord(done=0, running=0))  # 第 1 步(切 main)中断过
    result = await acc.accept()
    assert result.ota


async def test_finished_steps_are_skipped_on_retry(acc):
    """上次已经推送成功,只是后面失败了:重试不能再 push、不能再放一遍修复。"""
    acc.jenkins.failures["build_ota"] = RuntimeError("Jenkins 不可用")
    with pytest.raises(AcceptFailed):
        await acc.accept()
    pushed_before = acc.repos.origin_main()
    acc.jenkins.failures.clear()
    with pytest.raises(AcceptFailed, match="无法确认"):
        await acc.accept()
    await acc.accept()
    assert acc.repos.origin_main() == pushed_before  # 远端 main 没有因为重试再多出提交


async def test_retry_starts_progress_from_the_finished_steps(acc):
    acc.jenkins.failures["build_ota"] = RuntimeError("x")
    with pytest.raises(AcceptFailed):
        await acc.accept()
    acc.events.clear()
    acc.jenkins.failures.clear()
    with pytest.raises(AcceptFailed):  # 第一次重试被拦下
        await acc.accept()
    assert acc.events[0][0] == 4  # 显示从第 5 步开始,而不是从头


async def test_unfinished_accepts_are_listed_for_recovery_and_forgotten_when_done(acc):
    acc.progress.save("BUG-1", AcceptRecord(done=3, running=4))
    assert acc.accepter.unfinished() == {"BUG-1": 4}
    acc.progress.save("BUG-1", AcceptRecord(done=2))
    assert acc.accepter.unfinished() == {"BUG-1": 2}
    await acc.accepter.forget("BUG-1")
    assert acc.accepter.unfinished() == {}

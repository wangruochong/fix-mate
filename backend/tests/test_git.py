"""真实 git 的测试:在临时目录里建一个裸 origin、一个 FixMate 专用克隆、一个模拟同事的克隆。"""

import pytest

from fix_mate.adapters.git import ConflictError, GitError
from tests.git_helpers import Repos, run


@pytest.fixture
def repos(tmp_path):
    return Repos(tmp_path)


async def finished_fix(
    repos: Repos, defect_id: str = "BUG-1", file: str = "a.txt", content: str = "line1\nFIXED\nline3\n"
):
    """准备目录、写一个改动、整理成单个提交。返回整理结果。"""
    prepared = await repos.workspace.prepare(defect_id)
    (prepared.path / file).write_text(content)
    return await repos.workspace.finish(defect_id, f"fix: {defect_id}")


class TestFixPhase:
    async def test_prepare_creates_a_worktree_on_a_new_branch_from_origin_main(self, repos):
        p = await repos.workspace.prepare("BUG-1")
        assert p.path.exists() and p.branch == "fixmate/BUG-1"
        assert p.base_commit == repos.origin_main() and p.rebased is False
        assert run(p.path, "branch", "--show-current") == "fixmate/BUG-1"

    async def test_finish_squashes_everything_into_one_commit_and_reports_the_diff(self, repos):
        p = await repos.workspace.prepare("BUG-1")
        (p.path / "a.txt").write_text("line1\nSTEP1\nline3\n")
        await repos.workspace.save_progress("BUG-1")  # 中间暂停过一次,留下一个临时提交
        p = await repos.workspace.prepare("BUG-1")
        (p.path / "a.txt").write_text("line1\nFIXED\nline3\n")
        (p.path / "new.txt").write_text("hello\n")
        done = await repos.workspace.finish("BUG-1", "fix: BUG-1 登录页")

        assert not p.path.exists()  # 目录已删除
        assert run(repos.clone, "rev-list", "--count", f"{done.base_commit}..{done.commit}") == "1"
        assert run(repos.clone, "log", "-1", "--format=%s", done.commit) == "fix: BUG-1 登录页"
        files = await repos.workspace.diff(done.base_commit, done.commit)
        assert {f.name for f in files} == {"a.txt", "new.txt"}
        a = next(f for f in files if f.name == "a.txt")
        assert (a.additions, a.deletions) == (1, 1)

    async def test_branch_survives_removing_the_worktree(self, repos):
        await finished_fix(repos)
        assert run(repos.clone, "branch", "--list", "fixmate/BUG-1")

    async def test_save_progress_keeps_unfinished_work_and_resume_restores_it(self, repos):
        p = await repos.workspace.prepare("BUG-1")
        (p.path / "a.txt").write_text("line1\nHALF\nline3\n")
        (p.path / "draft.txt").write_text("未跟踪的新文件\n")
        await repos.workspace.save_progress("BUG-1")
        assert not p.path.exists()  # 脏目录不能直接删,所以先存成了提交

        again = await repos.workspace.prepare("BUG-1")
        assert (again.path / "a.txt").read_text() == "line1\nHALF\nline3\n"
        assert (again.path / "draft.txt").exists()

    async def test_save_progress_without_a_worktree_is_a_no_op(self, repos):
        await repos.workspace.save_progress("BUG-9")

    async def test_resume_rebases_onto_the_new_main_when_it_moved(self, repos):
        p = await repos.workspace.prepare("BUG-1")
        (p.path / "a.txt").write_text("FIRST\nline2\nline3\n")
        await repos.workspace.save_progress("BUG-1")
        repos.colleague_commit("b.txt", "别人的改动\n", "colleague work")  # main 前进了,改的是别的文件

        again = await repos.workspace.prepare("BUG-1")
        assert again.rebased is True and again.base_commit == repos.origin_main()
        assert (again.path / "b.txt").exists()  # 拿到了别人的改动
        assert (again.path / "a.txt").read_text().startswith("FIRST")  # 自己的改动还在

    async def test_resume_does_not_rebase_when_main_did_not_move(self, repos):
        p = await repos.workspace.prepare("BUG-1")
        (p.path / "a.txt").write_text("FIRST\nline2\nline3\n")
        await repos.workspace.save_progress("BUG-1")
        assert (await repos.workspace.prepare("BUG-1")).rebased is False

    async def test_rebase_conflict_is_aborted_and_reported(self, repos):
        p = await repos.workspace.prepare("BUG-1")
        (p.path / "a.txt").write_text("line1\nMINE\nline3\n")
        await repos.workspace.save_progress("BUG-1")
        repos.colleague_commit("a.txt", "line1\nTHEIRS\nline3\n", "same line")
        with pytest.raises(ConflictError):
            await repos.workspace.prepare("BUG-1")
        # 目录已被清掉,分支还在,仓库里没有半成品的变基状态
        assert not (repos.clone.parent / "worktrees" / "BUG-1").exists()
        assert run(repos.clone, "branch", "--list", "fixmate/BUG-1")
        assert run(repos.clone, "worktree", "list").count("\n") == 0  # 只剩主工作区

    async def test_prepare_is_safe_to_repeat_after_an_interruption(self, repos):
        """目录建好了、但还没来得及记录就中断,恢复后重跑 prepare 不能报错,也不能丢掉已有的改动。"""
        first = await repos.workspace.prepare("BUG-1")
        (first.path / "a.txt").write_text("line1\nWORK\nline3\n")
        again = await repos.workspace.prepare("BUG-1")
        assert again.path == first.path
        assert (again.path / "a.txt").read_text() == "line1\nWORK\nline3\n"

    async def test_a_branch_cannot_be_checked_out_in_two_places(self, repos):
        await repos.workspace.prepare("BUG-1")
        with pytest.raises(GitError):  # git 的限制:同一分支不能在两个目录检出
            await repos.workspace._git("worktree", "add", str(repos.clone.parent / "dup"), "fixmate/BUG-1")

    async def test_discard_removes_branch_and_directory(self, repos):
        p = await repos.workspace.prepare("BUG-1")
        (p.path / "a.txt").write_text("changed\n")
        await repos.workspace.discard("BUG-1")
        assert not p.path.exists() and run(repos.clone, "branch", "--list", "fixmate/BUG-1") == ""
        await repos.workspace.discard("BUG-1")  # 重复丢弃不报错

    async def test_unsafe_defect_ids_are_rejected(self, repos):
        for bad in ["../evil", "BUG-1; rm -rf /", "BUG-1/../x", "", "bug", "-delete"]:
            with pytest.raises(ValueError):
                await repos.workspace.prepare(bad)


class TestAcceptPhase:
    async def test_cherry_pick_and_push_put_the_fix_on_origin_main(self, repos):
        done = await finished_fix(repos)
        await repos.workspace.sync_main()
        await repos.workspace.cherry_pick(done.commit)
        final = await repos.workspace.push_main(done.commit)
        await repos.workspace.delete_branch("BUG-1")
        assert repos.origin_main() == final
        assert repos.origin_file("a.txt") == "line1\nFIXED\nline3"
        assert run(repos.clone, "branch", "--list", "fixmate/BUG-1") == ""

    async def test_sync_main_picks_up_new_commits_from_the_remote(self, repos):
        repos.colleague_commit("c.txt", "x\n", "c")
        await repos.workspace.sync_main()
        assert (repos.clone / "c.txt").exists()

    async def test_cherry_pick_is_safe_to_repeat(self, repos):
        """接受流程在这一步中断后重试,不能把同一个修复放进 main 两次。"""
        done = await finished_fix(repos)
        await repos.workspace.sync_main()
        first = await repos.workspace.cherry_pick(done.commit)
        count_after_first = run(repos.clone, "rev-list", "--count", "HEAD")
        again = await repos.workspace.cherry_pick(done.commit)
        assert again == first
        assert run(repos.clone, "rev-list", "--count", "HEAD") == count_after_first

    async def test_cherry_pick_is_safe_to_repeat_even_after_main_moved_on(self, repos):
        """修复已经放进 main 之后,main 上又有了别人的提交,重试仍然要认出「已经放过了」。"""
        done = await finished_fix(repos)
        repos.colleague_commit("b.txt", "别人的\n", "colleague")  # 让原提交的父提交不是当前 main,放进去会生成新提交
        await repos.workspace.sync_main()
        await repos.workspace.cherry_pick(done.commit)
        await repos.workspace.push_main(done.commit)
        repos.colleague_commit("c.txt", "又一个\n", "colleague again")
        await repos.workspace.sync_main()
        count = run(repos.clone, "rev-list", "--count", "HEAD")
        await repos.workspace.cherry_pick(done.commit)  # 重试
        assert run(repos.clone, "rev-list", "--count", "HEAD") == count

    async def test_cherry_pick_conflict_is_aborted_and_leaves_main_clean(self, repos):
        done = await finished_fix(repos)  # 改了第 2 行
        repos.colleague_commit("a.txt", "line1\nTHEIRS\nline3\n", "same line")  # 别人也改了第 2 行
        await repos.workspace.sync_main()
        before = run(repos.clone, "rev-parse", "HEAD")
        with pytest.raises(ConflictError):
            await repos.workspace.cherry_pick(done.commit)
        assert run(repos.clone, "status", "--porcelain") == ""  # 干净
        assert run(repos.clone, "rev-parse", "HEAD") == before  # main 没动

    async def test_rejected_push_is_redone_once_on_top_of_the_new_remote_main(self, repos):
        done = await finished_fix(repos)
        await repos.workspace.sync_main()
        await repos.workspace.cherry_pick(done.commit)
        repos.colleague_commit("b.txt", "别人的新提交\n", "colleague")  # 在我们推送前,远端有了新提交

        final = await repos.workspace.push_main(done.commit)
        assert repos.origin_main() == final
        assert repos.origin_file("b.txt") == "别人的新提交"  # 别人的提交没有被覆盖
        assert repos.origin_file("a.txt") == "line1\nFIXED\nline3"  # 我们的修复也在

    async def test_push_is_never_forced(self, repos):
        done = await finished_fix(repos)
        await repos.workspace.sync_main()
        await repos.workspace.cherry_pick(done.commit)
        repos.colleague_commit("a.txt", "line1\nTHEIRS\nline3\n", "conflicting")  # 重做时会冲突
        with pytest.raises(ConflictError):
            await repos.workspace.push_main(done.commit)
        assert repos.origin_file("a.txt") == "line1\nTHEIRS\nline3"  # 远端保持别人的版本,没有被覆盖

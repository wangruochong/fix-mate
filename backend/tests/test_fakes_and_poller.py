import asyncio

import pytest

from fix_mate.adapters.fakes import FakeCodeFixer, FakeFeishu, FakeJenkins
from fix_mate.services.poller import FeishuPoller
from tests.conftest import make_defect


def demo_file(root, defect_id, session_id):
    return root / "fixmate-demo" / f"{defect_id}-{session_id[-6:]}.md"


class TestFakeCodeFixer:
    async def test_assess_rejects_suggestions(self, tmp_path):
        fixer = FakeCodeFixer(delay=0)
        assert (await fixer.assess(make_defect("BUG-1"), tmp_path)).fixable is True
        assert (await fixer.assess(make_defect("SUG-1", type="建议"), tmp_path)).fixable is False

    async def test_fix_writes_a_file_and_reports_the_session(self, tmp_path):
        sessions = []
        report = await FakeCodeFixer(delay=0).fix(
            make_defect("BUG-1"), tmp_path, session_id=None, on_session=sessions.append, interrupt=asyncio.Event()
        )
        assert not report.interrupted and report.session_id == sessions[0]
        assert len(demo_file(tmp_path, "BUG-1", report.session_id).read_text().splitlines()) == 3

    async def test_interrupt_stops_early_and_resume_continues_the_same_work(self, tmp_path):
        fixer = FakeCodeFixer(delay=0)
        stop = asyncio.Event()
        stop.set()
        first = await fixer.fix(
            make_defect("BUG-1"), tmp_path, session_id=None, on_session=lambda _: None, interrupt=stop
        )
        assert first.interrupted is True

        resumed = await fixer.fix(
            make_defect("BUG-1"),
            tmp_path,
            session_id=first.session_id,
            on_session=lambda _: None,
            interrupt=asyncio.Event(),
        )
        assert not resumed.interrupted and resumed.session_id == first.session_id
        assert len(demo_file(tmp_path, "BUG-1", first.session_id).read_text().splitlines()) == 3  # 没有重复写

    async def test_a_fresh_session_always_produces_a_new_change(self, tmp_path):
        """全新处理一次必须有改动,即使以前处理过同一个缺陷(文件已经在 main 里)。"""
        fixer = FakeCodeFixer(delay=0)
        kw = {"on_session": lambda _: None, "interrupt": asyncio.Event()}
        one = await fixer.fix(make_defect("BUG-1"), tmp_path, session_id=None, **kw)
        two = await fixer.fix(make_defect("BUG-1"), tmp_path, session_id=None, **kw)
        assert demo_file(tmp_path, "BUG-1", one.session_id) != demo_file(tmp_path, "BUG-1", two.session_id)


class TestFakeServices:
    async def test_feishu_records_calls_and_can_fail_on_demand(self):
        feishu = FakeFeishu()
        await feishu.mark_resolved("BUG-1")
        await feishu.comment("BUG-1", "#3.8.0.1")
        assert feishu.resolved == ["BUG-1"] and feishu.comments == [("BUG-1", "#3.8.0.1")]
        feishu.failures["comment"] = RuntimeError("飞书不可用")
        with pytest.raises(RuntimeError):
            await feishu.comment("BUG-1", "x")

    async def test_jenkins_returns_increasing_versions(self):
        jenkins = FakeJenkins()
        assert [await jenkins.build_ota("a"), await jenkins.build_ota("b")] == ["3.8.0.2401", "3.8.0.2402"]


class TestPoller:
    async def test_new_defects_are_imported_once_and_notify(self, world):
        feishu = FakeFeishu([make_defect("BUG-9001")])
        poller = FeishuPoller(feishu, world.commands, interval=60)
        assert await poller.poll_once() == 1
        assert world.defect("BUG-9001").state == "queued"
        assert not any("BUG-9001" in x.defect_ids for x in world.commands.lists())  # 默认不在任何清单
        assert world.notifications()[0].title == "收到新缺陷 · 尚未加入清单"
        assert await poller.poll_once() == 0  # 再拉一次不会重复

    async def test_existing_defects_keep_their_local_state(self, world):
        feishu = FakeFeishu([make_defect("BUG-2481", state="queued")])  # 飞书上是旧状态
        await FeishuPoller(feishu, world.commands, interval=60).poll_once()
        assert world.defect("BUG-2481").state == "review"  # 本地的处理状态没有被覆盖

    async def test_many_new_defects_become_one_notification(self, world):
        feishu = FakeFeishu([make_defect(f"BUG-{9100 + i}") for i in range(5)])
        before = len(world.notifications())
        assert await FeishuPoller(feishu, world.commands, interval=60).poll_once() == 5
        assert len(world.notifications()) == before + 1

    async def test_failures_do_not_kill_the_polling_task(self, world):
        feishu = FakeFeishu()
        feishu.failures["fetch_assigned"] = RuntimeError("网络不通")
        poller = FeishuPoller(feishu, world.commands, interval=0.01)
        poller.start()
        await asyncio.sleep(0.05)
        del feishu.failures["fetch_assigned"]
        feishu.inbox.append(make_defect("BUG-9200"))
        for _ in range(100):  # 退避后会恢复
            if world.repo.get_defect("BUG-9200"):
                break
            await asyncio.sleep(0.05)
        await poller.stop()
        assert world.repo.get_defect("BUG-9200") is not None

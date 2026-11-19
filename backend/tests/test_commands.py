"""用户操作的行为测试。用例对应前端 `web/src/mock/mock.test.ts`,同一份行为在后端要同样成立。"""

from typing import ClassVar

import pytest

from fix_mate.services.errors import DomainError, NotFound


class TestAiProgress:
    async def test_defect_that_finishes_moves_to_review_and_next_one_starts(self, world):
        assert world.defect("BUG-2476").state == "analyzing"
        await world.advance(2)
        assert world.defect("BUG-2476").state == "review"
        assert world.defect("BUG-2469").state == "analyzing"
        assert world.defect("BUG-2469").step == 0

    async def test_fix_is_flagged_for_recheck_when_list_has_other_reviews(self, world):
        await world.advance(2)
        assert world.defect("BUG-2476").needs_recheck is True
        assert world.defect("BUG-2476").cached is not None

    async def test_step_is_reported_when_a_step_starts(self, world):
        assert world.defect("BUG-2469").state == "queued"
        await world.advance(2)  # 2476 走完
        await world.advance(1)
        assert world.defect("BUG-2469").step == 1

    async def test_suggestions_are_skipped_automatically(self, world):
        await world.commands.set_urgent("SUG-1120", "front")
        await world.advance(1)
        d = world.defect("SUG-1120")
        assert d.state == "passed"
        assert d.outcome.kind == "passed" and d.outcome.auto is True


class TestUrgent:
    async def test_front_interrupts_the_running_defect(self, world):
        await world.commands.set_urgent("BUG-2438", "front")
        await world.settle()
        assert world.defect("BUG-2438").state == "analyzing"
        paused = world.defect("BUG-2476")
        assert paused.state == "paused" and paused.pause.cause == "preempted"
        assert world.list_state("L-URGENT") == "running"
        assert world.list_state("L-0001") == "queued"

    async def test_interrupted_defect_resumes_from_its_step_after_urgent_is_done(self, world):
        await world.commands.set_urgent("BUG-2438", "front")
        await world.advance(3)
        assert world.defect("BUG-2438").state == "review"
        resumed = world.defect("BUG-2476")
        assert resumed.state == "analyzing" and resumed.step == 1
        assert resumed.rebased is None
        assert world.list_state("L-0001") == "running"

    async def test_resumed_defect_syncs_main_when_main_changed_meanwhile(self, world):
        await world.commands.set_urgent("BUG-2438", "front")
        await world.advance(3)
        await world.commands.set_urgent("BUG-2420", "front")
        await world.commands.accept("BUG-2438")
        await world.wait_until(lambda: world.defect("BUG-2438").state == "accepted")
        assert world.executor.main_rev == 1
        await world.advance(3)
        assert world.defect("BUG-2476").state == "analyzing"
        assert world.defect("BUG-2476").rebased is True

    async def test_back_does_not_interrupt_the_current_urgent_defect(self, world):
        await world.commands.set_urgent("BUG-2438", "front")
        await world.commands.set_urgent("BUG-2420", "back")
        await world.settle()
        assert world.defect("BUG-2438").state == "analyzing"
        assert world.defect("BUG-2420").state == "queued"

    async def test_finished_defects_cannot_be_made_urgent(self, world):
        with pytest.raises(DomainError):
            await world.commands.set_urgent("BUG-2455", "front")


class TestListQueue:
    async def test_pausing_a_list_saves_progress_and_resuming_continues(self, world):
        await world.commands.pause_list("L-0001")
        paused = world.defect("BUG-2476")
        assert paused.state == "paused" and paused.pause.cause == "user"
        assert world.list_state("L-0001") == "pending"
        await world.commands.start_list("L-0001")
        await world.settle()
        assert world.list_state("L-0001") == "running"
        assert world.defect("BUG-2476").state == "analyzing"

    async def test_starting_a_list_queues_it_without_interrupting_the_running_one(self, world):
        await world.commands.start_list("L-0002")
        assert world.list_state("L-0002") == "queued"
        assert world.list_state("L-0001") == "running"
        assert world.defect("BUG-2476").state == "analyzing"

    async def test_prioritize_moves_a_list_to_the_front(self, world):
        await world.commands.start_list("L-0002")
        await world.commands.prioritize_list("L-0002")
        await world.settle()
        assert world.list_state("L-0002") == "running"
        assert world.list_state("L-0001") == "queued"
        paused = world.defect("BUG-2476")
        assert paused.state == "paused" and paused.pause.cause == "preempted"
        assert world.defect("TST-0933").state == "analyzing"

    async def test_prioritize_on_a_pending_list_starts_and_jumps_the_queue(self, world):
        await world.commands.prioritize_list("L-0004")
        await world.settle()
        assert world.list_state("L-0004") == "running"
        assert world.list_state("L-0001") == "queued"

    async def test_done_list_restarts_when_a_new_undone_defect_is_added(self, world):
        await world.commands.add_to_list("L-0003", "BUG-2431")
        assert world.list_state("L-0003") == "queued"

    async def test_create_update_and_delete_a_list(self, world):
        list_id = await world.commands.create_list(" 新清单 ", ["BUG-2431"])
        created = next(x for x in world.commands.lists() if x.id == list_id)
        assert created.name == "新清单" and created.state == "pending"
        await world.commands.update_list(list_id, "改名", ["BUG-2431", "BUG-2420"])
        assert next(x for x in world.commands.lists() if x.id == list_id).defect_ids == ["BUG-2431", "BUG-2420"]
        await world.commands.delete_list(list_id)
        assert all(x.id != list_id for x in world.commands.lists())

    async def test_urgent_list_cannot_be_edited_or_deleted(self, world):
        with pytest.raises(DomainError, match="紧急清单不能删除"):
            await world.commands.delete_list("L-URGENT")
        with pytest.raises(DomainError, match="紧急清单不能编辑"):
            await world.commands.update_list("L-URGENT", "x", [])

    async def test_list_name_is_required(self, world):
        with pytest.raises(DomainError, match="请先给清单起个名字"):
            await world.commands.create_list("   ", [])

    async def test_deleting_the_running_list_pauses_its_defect(self, world):
        await world.commands.delete_list("L-0001")
        assert world.defect("BUG-2476").state == "paused"

    async def test_removing_the_running_defect_from_its_list_pauses_it_for_the_user(self, world):
        await world.commands.remove_from_list("L-0001", "BUG-2476")
        paused = world.defect("BUG-2476")
        assert paused.state == "paused" and paused.pause.cause == "user"
        # 清单里的下一个缺陷接着处理
        assert world.defect("BUG-2469").state == "analyzing"

    async def test_unknown_ids_are_reported(self, world):
        with pytest.raises(NotFound):
            await world.commands.start_list("L-9999")
        with pytest.raises(NotFound):
            await world.commands.add_to_list("L-0001", "NOPE")


class TestPauseAndResumeDefect:
    async def test_pausing_a_defect_pauses_its_running_list(self, world):
        await world.commands.pause_defect("BUG-2476")
        assert world.defect("BUG-2476").state == "paused"
        assert world.list_state("L-0001") == "pending"

    async def test_resuming_starts_the_list_again(self, world):
        await world.commands.pause_defect("BUG-2476")
        await world.commands.resume_defect("BUG-2476")
        await world.settle()
        assert world.defect("BUG-2476").state == "analyzing"


class TestReview:
    async def test_accept_runs_seven_steps_then_marks_accepted(self, world):
        await world.commands.accept("BUG-2481")
        await world.wait_until(lambda: world.defect("BUG-2481").state == "accepted")
        d = world.defect("BUG-2481")
        assert d.outcome.kind == "accepted" and d.outcome.ota.startswith("3.8.0.")
        assert world.executor.main_rev == 1

    async def test_accept_is_not_run_twice(self, world):
        await world.commands.accept("BUG-2481")
        await world.commands.accept("BUG-2481")
        await world.wait_until(lambda: world.defect("BUG-2481").state == "accepted")
        assert world.executor.main_rev == 1

    async def test_only_reviewed_defects_can_be_accepted(self, world):
        with pytest.raises(DomainError):
            await world.commands.accept("BUG-2469")

    async def test_recheck_clears_the_flag_and_records_the_result(self, world):
        await world.commands.recheck("BUG-2462")
        assert world.defect("BUG-2462").rechecking is True
        await world.wait_until(lambda: not world.defect("BUG-2462").rechecking)
        d = world.defect("BUG-2462")
        assert d.needs_recheck is False
        assert d.fix.recheck and d.fix.conflicts == []

    async def test_recheck_without_a_new_commit_keeps_the_real_commit(self, world):
        """真实引擎下复核不能把真实的提交号换成别的。"""
        from fix_mate.engine.stub import PlaceholderRechecker

        world.commands._rechecker = PlaceholderRechecker(speed=1000)
        before = world.defect("BUG-2462").fix.commit
        await world.commands.recheck("BUG-2462")
        await world.wait_until(lambda: not world.defect("BUG-2462").rechecking)
        assert world.defect("BUG-2462").fix.commit == before
        assert world.defect("BUG-2462").needs_recheck is False

    async def test_reject_can_keep_changes_and_trims_the_reason(self, world):
        await world.commands.reject("BUG-2481", True, "  范围偏大 ")
        out = world.defect("BUG-2481").outcome
        assert (out.kind, out.keep_changes, out.reason) == ("rejected", True, "范围偏大")

    async def test_pass_requires_a_reason(self, world):
        with pytest.raises(DomainError, match="必须写原因"):
            await world.commands.pass_("BUG-2481", "  ")
        await world.commands.pass_("BUG-2481", "无法复现")
        assert world.defect("BUG-2481").outcome.reason == "无法复现"


class TestNotifications:
    async def test_a_new_defect_is_not_in_any_list_and_notifies(self, world):
        before = len(world.notifications())
        d = await world.commands.simulate_new_defect()
        assert not any(d.id in x.defect_ids for x in world.commands.lists())
        assert len(world.notifications()) == before + 1

    async def test_quiet_feedback_is_not_stored(self, world):
        before = len(world.notifications())
        await world.commands.pause_list("L-0001")
        assert len(world.notifications()) == before

    async def test_mark_all_read(self, world):
        await world.commands.simulate_new_defect()
        await world.commands.mark_notifications_read()
        assert all(not n.unread for n in world.notifications())

    async def test_finishing_the_urgent_queue_notifies_and_the_list_resumes_quietly(self, world):
        await world.commands.set_urgent("BUG-2438", "front")
        await world.advance(3)
        titles = [n.title for n in world.notifications()]
        assert "紧急处理中" in titles
        assert "紧急缺陷已处理完" in titles


class TestReset:
    async def test_reset_restores_the_seed_data(self, world):
        await world.commands.simulate_new_defect()
        await world.commands.reset()
        await world.settle()
        assert len(world.commands.defects()) == 13
        assert world.list_state("L-0001") == "running"

    async def test_defect_that_was_processing_in_the_seed_really_runs_after_reset(self, world):
        """演示数据里有一个「处理中」的缺陷,重置后它必须真的在跑,而不是卡在原地。"""
        await world.commands.reset()
        await world.settle()
        await world.advance(2)
        assert world.defect("BUG-2476").state == "review"


class TestRecovery:
    async def test_defect_left_analyzing_by_a_crash_is_recovered(self, world):
        """进程异常退出后,数据库里有「处理中」的缺陷但没有执行器任务,重启后要能接着处理。"""
        from fix_mate.services.scheduler import Scheduler

        await world.scheduler.stop()
        d = world.defect("BUG-2476")
        assert d.state == "analyzing"  # 模拟崩溃:库里还是处理中
        fresh = Scheduler(world.repo, world.executor.__class__(interval=None, speed=1000), world.bus,
                          world.scheduler._notifier, lambda: d.created_at)  # fmt: skip
        await fresh.start()
        recovered = world.defect("BUG-2476")
        assert recovered.state == "analyzing" and recovered.step == 1  # 被恢复,从原来的步骤继续
        await fresh.stop()


class TestPauseRacingWithCompletion:
    async def test_a_fix_that_finished_just_before_the_pause_is_not_lost(self, world):
        """暂停请求到达时,这次处理恰好已经做完(结果还在消息队列里没被处理)。

        不能把缺陷标成「已暂停」而丢掉做完的修复。
        """
        import asyncio

        await world.advance(1)  # BUG-2476 走到最后一步前
        async with world.scheduler.lock:  # 占住锁:消费协程拿不到,「完成」的消息会一直留在队列里
            world.executor.advance()
            for _ in range(10):
                await asyncio.sleep(0)  # 让执行器的任务走完并汇报结果
            await world.scheduler.pause_now(world.defect("BUG-2476"), "user")
            await world.scheduler.reconcile()
        await world.settle()
        assert world.defect("BUG-2476").state == "review"
        assert world.defect("BUG-2476").fix is not None
        assert world.defect("BUG-2469").state == "analyzing"  # 接着处理清单里的下一个


class TestUserPausedDefects:
    async def test_starting_the_list_again_continues_the_defects_the_user_paused(self, world):
        """TST-0933 是用户手动暂停的,点清单的「继续处理」要真的接着做它。"""
        await world.commands.start_list("L-0002")
        assert world.list_state("L-0002") == "queued"
        await world.commands.prioritize_list("L-0002")
        await world.settle()
        assert world.defect("TST-0933").state == "analyzing"

    async def test_resuming_a_single_defect_continues_it(self, world):
        await world.commands.resume_defect("TST-0933")
        await world.commands.prioritize_list("L-0002")
        await world.settle()
        assert world.defect("TST-0933").state == "analyzing"
        assert world.defect("TST-0933").pause is None


class TestAcceptFailure:
    """接受失败不增加状态:缺陷仍是待审核,带着「卡在哪一步」,用户再点接受会重试。"""

    def failing_accepter(self, world, fail_times):
        from fix_mate.engine.ports import AcceptFailed, AcceptResult

        class Accepter:
            calls = 0
            forgotten: ClassVar[list[str]] = []

            async def accept(self, defect, on_progress):
                Accepter.calls += 1
                if Accepter.calls <= fail_times:
                    raise AcceptFailed(3, "推送到远端失败:网络不通")
                return AcceptResult(ota="3.8.0.9999", commit="abc1234")

            async def forget(self, defect_id):
                Accepter.forgotten.append(defect_id)

            def unfinished(self):
                return {"BUG-2481": 4}

        world.commands._accepter = Accepter()
        return Accepter

    async def test_a_failed_accept_keeps_the_defect_in_review_and_records_where_it_stopped(self, world):
        self.failing_accepter(world, fail_times=1)
        queue = world.bus.subscribe()
        await world.commands.accept("BUG-2481")
        await world.wait_until(lambda: world.defect("BUG-2481").accept_error is not None)

        d = world.defect("BUG-2481")
        assert d.state == "review"
        assert (d.accept_error.step, d.accept_error.message) == (3, "推送到远端失败:网络不通")
        events = []
        while not queue.empty():
            events.append(queue.get_nowait())
        assert any(e.type == "accept-progress" and e.error == "推送到远端失败:网络不通" and e.step == 3 for e in events)
        assert any(n.kind == "warn" and "接受 BUG-2481 失败" in n.title for n in world.notifications())

    async def test_retrying_clears_the_error_and_accepts(self, world):
        accepter = self.failing_accepter(world, fail_times=1)
        await world.commands.accept("BUG-2481")
        await world.wait_until(lambda: world.defect("BUG-2481").accept_error is not None)

        await world.commands.accept("BUG-2481")  # 用户再点一次
        await world.wait_until(lambda: world.defect("BUG-2481").state == "accepted")
        d = world.defect("BUG-2481")
        assert d.accept_error is None and d.outcome.ota == "3.8.0.9999"
        assert accepter.forgotten == ["BUG-2481"]  # 成功后清掉了接受进度

    async def test_unfinished_accepts_are_flagged_after_a_restart(self, world):
        self.failing_accepter(world, fail_times=0)
        await world.commands.recover_accepts()
        d = world.defect("BUG-2481")
        assert d.state == "review" and d.accept_error.step == 4
        assert "无法确认" in d.accept_error.message

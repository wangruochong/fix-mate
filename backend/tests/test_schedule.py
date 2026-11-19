"""调度规则的测试。用例来自前端 `web/src/mock/mock.test.ts` 里和纯规则相关的部分。"""

from fix_mate.domain.schedule import Decision, Pause, Start, active_list, decide, list_state, to_api_lists
from fix_mate.seed import seed_defects, seed_lists
from tests.conftest import by_id, make_defect, make_list


class TestSeedListStates:
    """种子数据推导出的清单状态,和前端一致。"""

    def setup_method(self):
        self.defects = {d.id: d for d in seed_defects()}
        self.lists = seed_lists()
        self.states = {x.id: x.state for x in to_api_lists(self.lists, self.defects)}

    def test_urgent_list_empty_is_pending(self):
        assert self.states["L-URGENT"] == "pending"  # 界面显示「空闲」

    def test_started_first_list_is_running(self):
        assert self.states["L-0001"] == "running"

    def test_paused_by_user_list_with_undone_defects_is_pending(self):
        assert self.states["L-0002"] == "pending"

    def test_list_without_undone_defects_is_done(self):
        assert self.states["L-0003"] == "done"

    def test_never_started_list_is_pending(self):
        assert self.states["L-0004"] == "pending"

    def test_urgent_list_comes_first(self):
        assert to_api_lists(self.lists, self.defects)[0].id == "L-URGENT"

    def test_seed_needs_no_scheduling_action(self):
        assert decide(self.lists, self.defects) == Decision()


class TestActiveList:
    def test_urgent_beats_lower_seq(self):
        ds = by_id(make_defect("a"), make_defect("u"))
        lists = [make_list("L1", ["a"], seq=1), make_list("U", ["u"], urgent=True, seq=0)]
        assert active_list(lists, ds).id == "U"

    def test_smallest_seq_among_started_lists(self):
        ds = by_id(make_defect("a"), make_defect("b"))
        lists = [make_list("L2", ["b"], seq=2), make_list("L1", ["a"], seq=1)]
        assert active_list(lists, ds).id == "L1"

    def test_not_started_or_finished_lists_are_not_active(self):
        ds = by_id(make_defect("a"), make_defect("b", "accepted"))
        lists = [make_list("off", ["a"], on=False), make_list("fin", ["b"])]
        assert active_list(lists, ds) is None

    def test_second_list_is_queued_while_first_runs(self):
        ds = by_id(make_defect("a"), make_defect("b"))
        lists = [make_list("L1", ["a"], seq=1), make_list("L2", ["b"], seq=2)]
        assert list_state(lists[0], lists, ds) == "running"
        assert list_state(lists[1], lists, ds) == "queued"

    def test_running_is_detected_for_a_separately_loaded_copy_of_the_list(self):
        ds = by_id(make_defect("a"))
        lists = [make_list("L1", ["a"])]
        copy = lists[0].model_copy()  # 从数据库重新读出来的是另一个对象
        assert list_state(copy, lists, ds) == "running"

    def test_empty_list_is_pending_not_done(self):
        lists = [make_list("E", [])]
        assert list_state(lists[0], lists, {}) == "pending"


class TestDecide:
    def test_starts_first_queued_defect_from_the_beginning(self):
        ds = by_id(make_defect("a", "accepted"), make_defect("b"), make_defect("c"))
        assert decide([make_list("L", ["a", "b", "c"])], ds) == Decision(start=Start("b", resume=False))

    def test_resumes_paused_defect_rather_than_starting_a_later_one(self):
        ds = by_id(make_defect("a", "paused"), make_defect("b"))
        assert decide([make_list("L", ["a", "b"])], ds) == Decision(start=Start("a", resume=True))

    def test_does_nothing_while_a_defect_is_already_running(self):
        ds = by_id(make_defect("a", "analyzing"), make_defect("b"))
        assert decide([make_list("L", ["a", "b"])], ds) == Decision()

    def test_defects_waiting_for_review_do_not_block_the_next_one(self):
        ds = by_id(make_defect("a", "review"), make_defect("b"))
        assert decide([make_list("L", ["a", "b"])], ds).start == Start("b", resume=False)

    def test_nothing_to_do_when_no_list_is_started(self):
        ds = by_id(make_defect("a"))
        assert decide([make_list("L", ["a"], on=False)], ds) == Decision()

    def test_urgent_defect_preempts_the_running_one(self):
        ds = by_id(make_defect("a", "analyzing"), make_defect("u"))
        lists = [make_list("L", ["a"], seq=1), make_list("U", ["u"], urgent=True, seq=0)]
        # 先只要求暂停,不会同时启动新缺陷
        assert decide(lists, ds) == Decision(pauses=(Pause("a", "preempted"),))

    def test_start_urgent_only_after_the_running_one_is_paused(self):
        ds = by_id(make_defect("a", "paused"), make_defect("u"))
        lists = [make_list("L", ["a"], seq=1), make_list("U", ["u"], urgent=True, seq=0)]
        assert decide(lists, ds) == Decision(start=Start("u", resume=False))

    def test_preempted_defect_resumes_after_urgent_is_done(self):
        ds = by_id(make_defect("a", "paused"), make_defect("u", "review"))
        lists = [make_list("L", ["a"], seq=1), make_list("U", ["u"], urgent=True, seq=0)]
        assert decide(lists, ds) == Decision(start=Start("a", resume=True))

    def test_defect_removed_from_all_started_lists_is_paused_by_user(self):
        ds = by_id(make_defect("a", "analyzing"), make_defect("b"))
        lists = [make_list("L", ["b"])]  # a 已不在任何清单里
        assert decide(lists, ds) == Decision(pauses=(Pause("a", "user"),))

    def test_defect_kept_in_another_started_list_counts_as_preempted(self):
        ds = by_id(make_defect("a", "analyzing"), make_defect("b"))
        lists = [make_list("first", ["b"], seq=1), make_list("second", ["a"], seq=2)]
        assert decide(lists, ds) == Decision(pauses=(Pause("a", "preempted"),))

    def test_defect_listed_in_both_urgent_and_normal_list_keeps_running(self):
        ds = by_id(make_defect("a", "analyzing"))
        lists = [make_list("L", ["a"], seq=1), make_list("U", ["a"], urgent=True, seq=0)]
        assert decide(lists, ds) == Decision()


class TestWaitingForTheUser:
    """用户手动暂停的(包括处理出错的)缺陷要等用户点继续,调度不能自作主张。"""

    def user_paused(self, id):
        from fix_mate.domain.models import PauseInfo
        from tests.conftest import NOW

        return make_defect(id, "paused", pause=PauseInfo(cause="user", at=NOW))

    def test_user_paused_defects_are_skipped_and_the_next_one_runs(self):
        ds = by_id(self.user_paused("a"), make_defect("b"))
        assert decide([make_list("L", ["a", "b"])], ds) == Decision(start=Start("b", resume=False))

    def test_a_list_with_only_waiting_defects_does_nothing(self):
        ds = by_id(self.user_paused("a"))
        assert decide([make_list("L", ["a"])], ds) == Decision()

    def test_such_a_list_is_pending_so_it_does_not_block_the_lists_behind_it(self):
        ds = by_id(self.user_paused("a"), make_defect("b"))
        lists = [make_list("first", ["a"], seq=1), make_list("second", ["b"], seq=2)]
        assert list_state(lists[0], lists, ds) == "pending"
        assert list_state(lists[1], lists, ds) == "running"  # 排在后面的清单照常处理
        assert decide(lists, ds) == Decision(start=Start("b", resume=False))

    def test_preempted_pauses_resume_automatically(self):
        from fix_mate.domain.models import PauseInfo
        from tests.conftest import NOW

        ds = by_id(make_defect("a", "paused", pause=PauseInfo(cause="preempted", at=NOW)))
        assert decide([make_list("L", ["a"])], ds) == Decision(start=Start("a", resume=True))

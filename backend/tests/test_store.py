"""存储层测试:数据必须真的写进磁盘,重启后还在。"""

from fix_mate.store.db import MIGRATIONS, open_database
from fix_mate.store.repository import Repository
from tests.conftest import make_defect, make_list


def test_writes_outside_a_transaction_survive_reopening(tmp_path):
    path = tmp_path / "fixmate.db"
    repo = Repository(open_database(path))
    repo.save_defect(make_defect("A"))
    repo.save_list(make_list("L1", ["A"]))
    # 不显式提交,直接换一个新连接读取(相当于进程退出后重新启动)
    other = Repository(open_database(path))
    assert [d.id for d in other.all_defects()] == ["A"]
    assert [r.id for r in other.all_lists()] == ["L1"]


def test_transaction_rolls_back_on_error(tmp_path):
    repo = Repository(open_database(tmp_path / "fixmate.db"))
    try:
        with repo.transaction():
            repo.save_defect(make_defect("A"))
            raise RuntimeError("中途出错")
    except RuntimeError:
        pass
    assert repo.all_defects() == []


def test_transaction_commits_all_changes_together(tmp_path):
    path = tmp_path / "fixmate.db"
    repo = Repository(open_database(path))
    with repo.transaction():
        repo.save_defect(make_defect("A"))
        repo.save_defect(make_defect("B"))
    assert len(Repository(open_database(path)).all_defects()) == 2


def test_list_keeps_its_position_when_updated(tmp_path):
    repo = Repository(open_database(tmp_path / "fixmate.db"))
    repo.save_list(make_list("L1", []))
    repo.save_list(make_list("L2", []))
    updated = make_list("L1", ["x"])
    repo.save_list(updated)
    assert [r.id for r in repo.all_lists()] == ["L1", "L2"]


def test_counters_do_not_repeat(tmp_path):
    repo = Repository(open_database(tmp_path / "fixmate.db"))
    assert [repo.next_counter("n") for _ in range(3)] == [1, 2, 3]
    assert repo.next_counter("other") == 1


def test_schema_version_is_recorded_and_reopening_does_not_migrate_twice(tmp_path):
    path = tmp_path / "fixmate.db"
    assert open_database(path).execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)
    assert open_database(path).execute("PRAGMA user_version").fetchone()[0] == len(MIGRATIONS)  # 重复打开不会重复建表


def test_session_ids_are_saved_and_replaced(tmp_path):
    repo = Repository(open_database(tmp_path / "fixmate.db"))
    assert repo.get_session_id("BUG-1") is None
    repo.save_session_id("BUG-1", "s1")
    repo.save_session_id("BUG-1", "s2")
    assert repo.get_session_id("BUG-1") == "s2"


def test_nested_transactions_commit_once_at_the_outermost(tmp_path):
    path = tmp_path / "fixmate.db"
    repo = Repository(open_database(path))
    with repo.transaction():
        repo.save_defect(make_defect("A"))
        with repo.transaction():
            repo.save_defect(make_defect("B"))
        assert Repository(open_database(path)).all_defects() == []  # 还没提交,别的连接看不到
    assert len(Repository(open_database(path)).all_defects()) == 2

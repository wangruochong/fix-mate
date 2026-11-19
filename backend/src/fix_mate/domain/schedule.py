"""调度规则:纯函数,不碰数据库、不碰 AI、不碰 git。

规则来自设计文档第 3、4、5 节:

- 同一时间只有一个 AI 执行者。
- 活跃清单 = 紧急清单优先,否则是排在最前的、已开始的清单。
- 清单状态完全由缺陷状态和清单的开始标记推导,不单独存储。

这里只回答「现在该做什么」,真正去暂停、去启动由 `services/scheduler.py` 执行。
"""

from dataclasses import dataclass

from fix_mate.domain.models import (
    Defect,
    DefectList,
    ListRecord,
    ListState,
    PauseCause,
)

DefectsById = dict[str, Defect]


def _defects_of(record: ListRecord, defects: DefectsById) -> list[Defect]:
    """清单里的缺陷,按清单顺序;找不到的(已被删除)忽略。"""
    return [defects[i] for i in record.defect_ids if i in defects]


def has_undone(record: ListRecord, defects: DefectsById) -> bool:
    """还有没处理完的缺陷(包括在等用户手动继续的)。"""
    return any(d.is_undone for d in _defects_of(record, defects))


def is_runnable(defect: Defect) -> bool:
    """AI 可以自己去做的缺陷:排队中、正在处理、或者会自动恢复的暂停。

    用户手动暂停的(包括处理出错的)不算:它们要等用户明确点「继续」,调度不能自作主张重试,
    否则出错的缺陷会无限重试,也会挡住排在后面的清单。
    """
    if defect.state in ("queued", "analyzing"):
        return True
    return defect.state == "paused" and (defect.pause is None or defect.pause.cause != "user")


def has_work(record: ListRecord, defects: DefectsById) -> bool:
    """清单里有没有 AI 现在能做的活。"""
    return any(is_runnable(d) for d in _defects_of(record, defects))


def active_list(lists: list[ListRecord], defects: DefectsById) -> ListRecord | None:
    """当前被 AI 处理的清单:紧急清单优先,否则取 seq 最小的。只看有活可做的清单。"""
    candidates = [r for r in lists if r.on and has_work(r, defects)]
    urgent = [r for r in candidates if r.urgent]
    if urgent:
        return urgent[0]
    return min(candidates, key=lambda r: r.seq, default=None)


def list_state(record: ListRecord, lists: list[ListRecord], defects: DefectsById) -> ListState:
    if not has_undone(record, defects):
        # 空清单还没东西可处理,算待处理;有缺陷且都处理完了才算完成
        return "pending" if not record.defect_ids else "done"
    if not record.on or not has_work(record, defects):
        # 没开始/被暂停;或者剩下的都在等用户手动继续:都是「待处理」,等用户点继续
        return "pending"
    active = active_list(lists, defects)
    # 按 id 比较:调用方每次可能从数据库重新读出清单对象,不能用对象身份
    return "running" if active is not None and active.id == record.id else "queued"


def to_api_lists(lists: list[ListRecord], defects: DefectsById) -> list[DefectList]:
    """转成对外的清单:紧急清单置顶,其余保持原顺序,并带上推导出的状态。"""
    ordered = sorted(lists, key=lambda r: not r.urgent)  # sorted 是稳定排序
    return [
        DefectList(
            id=r.id,
            name=r.name,
            urgent=True if r.urgent else None,
            created_at=r.created_at,
            defect_ids=list(r.defect_ids),
            state=list_state(r, lists, defects),
        )
        for r in ordered
    ]


# ------------------------------------------------------------------ 调度决策


@dataclass(frozen=True)
class Pause:
    """要暂停一个正在处理的缺陷。cause 决定恢复方式:被插队的自动恢复,用户暂停的要手动继续。"""

    defect_id: str
    cause: PauseCause


@dataclass(frozen=True)
class Start:
    """要开始处理一个缺陷。resume 为 True 表示从暂停处继续,否则从头开始。"""

    defect_id: str
    resume: bool


@dataclass(frozen=True)
class Decision:
    """一次调度的结论。pauses 和 start 不会同时出现:

    暂停需要时间(要等当前步骤停下),必须先确认旧缺陷停了,才能启动新的,
    否则会同时有两个执行者。所以有人要暂停时只返回 pauses,等暂停完成后再决定一次。
    """

    pauses: tuple[Pause, ...] = ()
    start: Start | None = None


def decide(lists: list[ListRecord], defects: DefectsById) -> Decision:
    """根据当前所有清单和缺陷,决定现在该暂停谁、或该开始处理谁。

    每次状态可能变化之后都要重新调用:用户操作、缺陷处理完成、暂停完成、收到新缺陷。
    """
    active = active_list(lists, defects)
    active_ids = set(active.defect_ids) if active else set()

    # 1. 不在活跃清单里的处理中缺陷要让位。
    #    它还在某个已开始的清单里 → 是被插队;否则是用户操作(如移出了清单)造成的。
    pauses = tuple(
        Pause(d.id, "preempted" if any(r.on and d.id in r.defect_ids for r in lists) else "user")
        for d in defects.values()
        if d.state == "analyzing" and d.id not in active_ids
    )
    if pauses:
        return Decision(pauses=pauses)

    # 2. 活跃清单里已经有缺陷在处理,保持不变
    if active is None or any(d.state == "analyzing" for d in _defects_of(active, defects)):
        return Decision()

    # 3. 取活跃清单里第一个能自动做的缺陷;已暂停的接着做,排队的从头做
    for d in _defects_of(active, defects):
        if d.state in ("queued", "paused") and is_runnable(d):
            return Decision(start=Start(d.id, resume=d.state == "paused"))
    return Decision()

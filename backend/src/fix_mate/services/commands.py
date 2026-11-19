"""用户的所有操作。每个方法对应一个接口(见 web/README.md 的接口表)。

写法统一:
    async with self._scheduler.lock:   # 同一时间只允许一个修改
        改数据 → 存库
        await self._scheduler.reconcile()   # 数据变了,重新决定该处理谁
        发提示

业务规则(状态怎么流转)在 domain/ 和 scheduler.py;这里只负责校验、修改数据、给用户反馈。
"""

import asyncio
import contextlib
import logging
import re
from collections.abc import Callable
from datetime import datetime
from typing import Literal

from fix_mate.domain.models import (
    Accepted,
    AcceptError,
    AcceptProgressEvent,
    AppNotification,
    Defect,
    DefectList,
    ListRecord,
    Passed,
    Rejected,
)
from fix_mate.domain.schedule import list_state, to_api_lists
from fix_mate.engine.ports import Accepter, AcceptFailed, Rechecker
from fix_mate.seed import seed_defects, seed_lists
from fix_mate.services.errors import DomainError, NotFound
from fix_mate.services.events import EventBus
from fix_mate.services.notifier import Notifier
from fix_mate.services.scheduler import Scheduler
from fix_mate.store.repository import Repository

log = logging.getLogger(__name__)

#: 开发调试用:模拟从飞书收到的新缺陷
_NEW_DEFECT_POOL = [
    ("启动页偶现白屏超过 3 秒", "Bug", "Critical", "账号体系改版", "v3.8.0"),
    ("订单列表筛选后分页错乱", "Bug", "Major", "支付链路优化 · 海外多币种结算与风控联动改造(二期)", "v3.8.0"),
    ("希望增加更多主题配色", "建议", "Minor", "设置页重构", "v3.8.0"),
]


class Commands:
    def __init__(
        self,
        repo: Repository,
        scheduler: Scheduler,
        accepter: Accepter,
        rechecker: Rechecker,
        bus: EventBus,
        notifier: Notifier,
        clock: Callable[[], datetime],
    ):
        self._repo = repo
        self._scheduler = scheduler
        self._accepter = accepter
        self._rechecker = rechecker
        self._bus = bus
        self._notifier = notifier
        self._clock = clock
        self._accepting: set[str] = set()
        self._tasks: set[asyncio.Task] = set()

    # ---------------------------------------------------------------- 查询

    def defects(self) -> list[Defect]:
        return self._repo.all_defects()

    def defect(self, defect_id: str) -> Defect:
        return self._get_defect(defect_id)

    def lists(self) -> list[DefectList]:
        return to_api_lists(self._repo.all_lists(), self._defects_by_id())

    def notifications(self) -> list[AppNotification]:
        return self._repo.notifications()

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._tasks):
            with contextlib.suppress(asyncio.CancelledError):
                await task

    # ---------------------------------------------------------------- 清单

    def _allow_auto_resume(self, defects: list[Defect]) -> None:
        """用户明确要求继续时,把「等用户手动继续」的暂停(含处理出错的)改成可自动恢复。

        调度只会自动处理可恢复的缺陷;不先转换,用户点「继续」也不会真的继续它们。
        """
        for d in defects:
            if d.state == "paused" and d.pause and d.pause.cause == "user":
                d.pause.cause = "preempted"
                self._repo.save_defect(d)

    async def start_list(self, list_id: str) -> None:
        """开始或继续一个清单:排到处理队列队尾,不打断正在处理的清单。"""
        async with self._scheduler.lock:
            record = self._get_list(list_id)
            if self._state_of(record) in ("running", "queued"):
                return
            resumed = any(d.state != "queued" for d in self._defects_in(record))
            self._allow_auto_resume(self._defects_in(record))
            record.on = True
            record.seq = self._next_seq()
            self._repo.save_list(record)
            await self._scheduler.reconcile()

            after = self._state_of(record)
            running = next((x for x in self.lists() if x.state == "running"), None)
            if after == "running":
                self._notifier.notify(
                    f"{'继续' if resumed else '开始'}处理「{record.name}」", "AI 会按顺序逐个修复", "new", quiet=True
                )
            elif after == "queued" and running:
                self._notifier.notify(
                    f"「{record.name}」已加入处理队列",
                    f"前面还有「{running.name}」,轮到后会自动开始",
                    "new",
                    quiet=True,
                )

    async def pause_list(self, list_id: str) -> None:
        async with self._scheduler.lock:
            record = self._get_list(list_id)
            record.on = False
            self._repo.save_list(record)
            await self._scheduler.reconcile()
            self._notifier.notify(f"已暂停「{record.name}」", "进度已保存,继续时从暂停处接着处理", "skip", quiet=True)

    async def prioritize_list(self, list_id: str) -> None:
        """让清单插到队首,正在处理的清单暂时让位。对待处理的清单点优先处理,等于开始并插队。"""
        async with self._scheduler.lock:
            record = self._get_list(list_id)
            before = next((x for x in self.lists() if x.state == "running"), None)
            started = [r.seq for r in self._repo.all_lists() if r.on and not r.urgent]
            self._allow_auto_resume(self._defects_in(record))
            record.on = True
            record.seq = (min(started) if started else 1) - 1
            self._repo.save_list(record)
            await self._scheduler.reconcile()
            yielded = before is not None and before.id != record.id
            body = f"「{before.name}」暂时让位,进度已保存" if yielded and before else "AI 会按顺序逐个修复"
            self._notifier.notify(f"已优先处理「{record.name}」", body, "new", quiet=True)

    async def create_list(self, name: str, defect_ids: list[str]) -> str:
        name = self._valid_name(name)
        async with self._scheduler.lock:
            ids = [r.id for r in self._repo.all_lists()]
            number = max((int(m.group(1)) for i in ids if (m := re.fullmatch(r"L-(\d+)", i))), default=0) + 1
            record = ListRecord(
                id=f"L-{number:04d}", name=name, created_at=self._clock(), defect_ids=list(dict.fromkeys(defect_ids))
            )
            self._repo.save_list(record)
            await self._scheduler.reconcile()
            self._notifier.notify(
                f"已创建清单「{name}」",
                f"{len(record.defect_ids)} 个缺陷 · 点击卡片即可查看并开始处理",
                "ok",
                quiet=True,
            )
            return record.id

    async def update_list(self, list_id: str, name: str, defect_ids: list[str]) -> None:
        name = self._valid_name(name)
        async with self._scheduler.lock:
            record = self._get_list(list_id)
            if record.urgent:
                raise DomainError("紧急清单不能编辑")
            record.name = name
            record.defect_ids = list(dict.fromkeys(defect_ids))
            self._repo.save_list(record)
            await self._scheduler.reconcile()
            self._notifier.notify(f"已保存「{name}」", f"{len(record.defect_ids)} 个缺陷", "ok", quiet=True)

    async def delete_list(self, list_id: str) -> None:
        async with self._scheduler.lock:
            record = self._get_list(list_id)
            if record.urgent:
                raise DomainError("紧急清单不能删除")
            self._repo.delete_list(list_id)  # 正在处理的缺陷会在 reconcile 里被暂停并保存进度
            await self._scheduler.reconcile()
            self._notifier.notify(f"已删除清单「{record.name}」", "清单里的缺陷仍可以在搜索中找到", "skip", quiet=True)

    async def add_to_list(self, list_id: str, defect_id: str) -> None:
        async with self._scheduler.lock:
            record = self._get_list(list_id)
            defect = self._get_defect(defect_id)
            was = self._state_of(record)
            if defect_id not in record.defect_ids:
                record.defect_ids.append(defect_id)
            # 处理完成的清单加入新的未处理缺陷后,自动排到队尾
            if was == "done" and defect.is_undone and record.on:
                record.seq = self._next_seq()
            self._repo.save_list(record)
            now = self._state_of(record)
            if was == "done" and defect.is_undone:
                message = {
                    "running": "清单已自动重新开始处理,AI 会处理新加入的缺陷",
                    "queued": "清单重新进入处理队列,轮到后会自动处理",
                }.get(now, "清单保持暂停,继续后会处理它")
            elif now == "running":
                message = "已排到清单末尾,会按顺序处理"
            else:
                message = defect_id
            await self._scheduler.reconcile()
            self._notifier.notify(f"已添加到「{record.name}」", message, "ok", quiet=True)

    async def remove_from_list(self, list_id: str, defect_id: str) -> None:
        async with self._scheduler.lock:
            record = self._get_list(list_id)
            record.defect_ids = [i for i in record.defect_ids if i != defect_id]
            self._repo.save_list(record)
            await self._scheduler.reconcile()
            self._notifier.notify(f"已从「{record.name}」中删除", defect_id, "skip", quiet=True)

    # ---------------------------------------------------------------- 缺陷处理

    async def pause_defect(self, defect_id: str) -> None:
        async with self._scheduler.lock:
            defect = self._get_defect(defect_id)
            running = next(
                (r for r in self._repo.all_lists() if defect_id in r.defect_ids and self._state_of(r) == "running"),
                None,
            )
            if running:  # 暂停缺陷等于暂停它所在的正在处理的清单
                running.on = False
                self._repo.save_list(running)
                await self._scheduler.reconcile()
                self._notifier.notify(
                    f"已暂停「{running.name}」", "进度已保存,继续时从暂停处接着处理", "skip", quiet=True
                )
            elif defect.state == "analyzing":
                await self._scheduler.pause_now(defect, "user")
                await self._scheduler.reconcile()

    async def resume_defect(self, defect_id: str) -> None:
        async with self._scheduler.lock:
            self._allow_auto_resume([self._get_defect(defect_id)])
            mine = [r for r in self._repo.all_lists() if defect_id in r.defect_ids]
            target = (
                next((r for r in mine if self._state_of(r) == "pending"), None)
                or next((r for r in mine if self._state_of(r) in ("running", "queued")), None)
                or (mine[0] if mine else None)
            )
        if target:
            await self.start_list(target.id)

    async def set_urgent(self, defect_id: str, position: Literal["front", "back"]) -> None:
        """立即处理:加入紧急清单。front 会打断当前的紧急缺陷,back 排在紧急队列后面。"""
        async with self._scheduler.lock:
            defect = self._get_defect(defect_id)
            if not defect.is_undone:
                raise DomainError("这个缺陷已经处理完了,不需要立即处理")
            urgent = self._urgent_list()
            if position == "front":
                urgent.defect_ids = [defect_id, *[i for i in urgent.defect_ids if i != defect_id]]
            elif defect_id not in urgent.defect_ids:
                urgent.defect_ids.append(defect_id)
            urgent.on = True
            self._repo.save_list(urgent)
            self._allow_auto_resume([defect])
            if position == "front":  # 打断正在处理的其它紧急缺陷
                for other in self._defects_in(urgent):
                    if other.state == "analyzing" and other.id != defect_id:
                        await self._scheduler.pause_now(other, "preempted")
            await self._scheduler.reconcile()
            where = "马上开始处理" if position == "front" else "会在紧急队列中依次处理"
            self._notifier.notify("已加入紧急处理", f"{defect_id} {where}", "warn", quiet=True)

    # ---------------------------------------------------------------- 审核

    async def reject(self, defect_id: str, keep_changes: bool, reason: str | None) -> None:
        async with self._scheduler.lock:
            defect = self._get_review_defect(defect_id)
            defect.state = "rejected"
            defect.outcome = Rejected(keep_changes=keep_changes, reason=(reason or "").strip() or None)
            self._repo.save_defect(defect)
            if not keep_changes:  # 丢弃:删掉它的分支和检查点。保留修改的做法见设计文档第 6 节(待实现)
                await self._scheduler.discard_progress(defect_id)
            await self._scheduler.reconcile()
            self._notifier.notify(
                f"已拒绝 {defect_id}", "AI 修改已保留到工作区" if keep_changes else "AI 修改已丢弃", "skip"
            )

    async def pass_(self, defect_id: str, reason: str) -> None:
        reason = reason.strip()
        if not reason:
            raise DomainError("跳过必须写原因")
        async with self._scheduler.lock:
            defect = self._get_review_defect(defect_id)
            defect.state = "passed"
            defect.outcome = Passed(auto=False, reason=reason)
            self._repo.save_defect(defect)
            await self._scheduler.reconcile()
            self._notifier.notify(f"已跳过 {defect_id}", reason, "skip")

    async def accept(self, defect_id: str) -> None:
        """接受方案。接受流程耗时较长,在后台执行,进度通过事件流汇报。"""
        async with self._scheduler.lock:
            defect = self._get_review_defect(defect_id)
            if defect_id in self._accepting:
                return
            self._accepting.add(defect_id)
        self._spawn(self._run_accept(defect))

    async def _run_accept(self, defect: Defect) -> None:
        def progress(step: int, ota: str | None) -> None:
            self._bus.publish(AcceptProgressEvent(defect_id=defect.id, step=step, ota=ota))

        async with self._scheduler.lock:  # 重试时,先清掉上一次的失败提示
            fresh = self._get_defect(defect.id)
            if fresh.accept_error:
                fresh.accept_error = None
                self._repo.save_defect(fresh)
                self._bus.changed()

        try:
            result = await self._accepter.accept(defect, progress)
        except AcceptFailed as e:
            await self._record_accept_failure(defect.id, e.step, e.message)
            return
        except Exception as e:  # 别的执行器抛出的未知错误也要汇报给用户,不能让后台任务悄悄死掉
            log.exception("接受 %s 失败", defect.id)
            await self._record_accept_failure(defect.id, 0, str(e))
            return

        async with self._scheduler.lock:
            fresh = self._get_defect(defect.id)
            fresh.state = "accepted"
            fresh.needs_recheck = None
            fresh.accept_error = None
            fresh.outcome = Accepted(ota=result.ota, commit=result.commit)
            self._repo.save_defect(fresh)
            self._accepting.discard(defect.id)
            await self._accepter.forget(defect.id)  # 状态已保存,接受进度可以清掉了
            await self._scheduler.discard_progress(defect.id)  # 修复阶段留下的检查点也不再需要
            self._bus.publish(AcceptProgressEvent(defect_id=defect.id, step=7, ota=result.ota))
            await self._scheduler.reconcile()
            self._notifier.notify(
                f"已接受 {defect.id}", f"OTA {result.ota} 已打包,飞书已评论 #{result.ota}", "ok", defect.id
            )

    async def _record_accept_failure(self, defect_id: str, step: int, message: str) -> None:
        """接受失败:缺陷仍是待审核,记下卡在哪一步和原因,用户再点接受会从这一步继续。"""
        async with self._scheduler.lock:
            fresh = self._get_defect(defect_id)
            fresh.accept_error = AcceptError(step=step, message=message)
            self._repo.save_defect(fresh)
            self._accepting.discard(defect_id)
            self._bus.publish(AcceptProgressEvent(defect_id=defect_id, step=step, error=message))
            self._notifier.notify(f"接受 {defect_id} 失败", message, "warn", defect_id)
            self._bus.changed()

    async def recover_accepts(self) -> None:
        """启动时调用:上次程序退出时还在接受中的缺陷,标出卡在哪一步,让用户确认后重试。"""
        async with self._scheduler.lock:
            for defect_id, step in self._accepter.unfinished().items():
                defect = self._repo.get_defect(defect_id)
                if defect is None or defect.state != "review":
                    await self._accepter.forget(defect_id)  # 缺陷已经不在待审核,这份进度是过期的
                    continue
                defect.accept_error = AcceptError(
                    step=step,
                    message="上次接受到这一步时程序中断了,无法确认这一步是否已经生效。请先检查,再点「重试接受」。",
                )
                self._repo.save_defect(defect)
                self._notifier.notify(f"接受 {defect_id} 上次没有做完", defect.accept_error.message, "warn", defect_id)

    async def recheck(self, defect_id: str) -> None:
        async with self._scheduler.lock:
            defect = self._get_review_defect(defect_id)
            if defect.rechecking:
                return
            defect.rechecking = True
            self._repo.save_defect(defect)
            self._bus.changed()
        self._spawn(self._run_recheck(defect))

    async def _run_recheck(self, defect: Defect) -> None:
        text, commit = await self._rechecker.recheck(defect)
        async with self._scheduler.lock:
            fresh = self._get_defect(defect.id)
            if fresh.fix is None:
                return
            fresh.rechecking = False
            fresh.needs_recheck = False
            fresh.fix.recheck = text
            fresh.fix.conflicts = []
            if commit is not None:  # 方案有变化才换提交;没有变化就保持原样
                fresh.fix.commit = commit
            self._repo.save_defect(fresh)
            self._bus.changed()
            self._notifier.notify("复核完成", f"{defect.id} 的方案已基于最新代码更新", "ok", defect.id)

    # ---------------------------------------------------------------- 通知

    async def mark_notifications_read(self) -> None:
        async with self._scheduler.lock:
            self._repo.mark_notifications_read()
            self._bus.changed()

    # ---------------------------------------------------------------- 开发调试(仅 dev 模式)

    async def simulate_new_defect(self) -> Defect:
        """模拟从飞书收到一个新缺陷,默认不在任何清单里。"""
        async with self._scheduler.lock:
            n = self._repo.next_counter("simulated_defect")
            title, type_, priority, requirement, version = _NEW_DEFECT_POOL[(n - 1) % len(_NEW_DEFECT_POOL)]
            defect = Defect(
                id=f"{'SUG' if type_ == '建议' else 'BUG'}-{2490 + n}",
                title=title,
                type=type_,  # type: ignore[arg-type]
                priority=priority,  # type: ignore[arg-type]
                requirement=requirement,
                version=version,
                reporter="飞书同学",
                created_at=self._clock(),
                description=f"(模拟的新缺陷){title}。",
                state="queued",
            )
            self._repo.save_defect(defect)
            self._notifier.notify(
                "收到新缺陷 · 尚未加入清单", f"{defect.id} · {defect.priority} · {defect.title}", "warn", defect.id
            )
            self._bus.changed()
            return defect

    async def import_defects(self, incoming: list[Defect]) -> int:
        """导入从飞书拉取到的缺陷。已存在的不覆盖(处理状态以本地为准),返回新增的数量。"""
        async with self._scheduler.lock:
            known = {d.id for d in self._repo.all_defects()}
            new = [d for d in incoming if d.id not in known]
            if not new:
                return 0
            with self._repo.transaction():
                for d in new:
                    self._repo.save_defect(d)
            if len(new) == 1:
                d = new[0]
                self._notifier.notify("收到新缺陷 · 尚未加入清单", f"{d.id} · {d.priority} · {d.title}", "warn", d.id)
            else:  # 第一次同步可能一下子来很多,合并成一条,不刷屏
                self._notifier.notify("收到新缺陷 · 尚未加入清单", f"共 {len(new)} 条,请到清单页归类", "warn")
            self._bus.changed()
            return len(new)

    async def add_defects(self, defects: list[Defect]) -> None:
        async with self._scheduler.lock:
            with self._repo.transaction():
                for d in defects:
                    self._repo.save_defect(d)
            self._bus.changed()

    async def reset(self) -> None:
        """清空并重新灌入演示数据。"""
        async with self._scheduler.lock:
            await self._scheduler.halt()
            for old in self._repo.all_defects():
                await self._scheduler.discard_progress(old.id)  # 旧的分支和检查点不能带到新的演示数据里
            with self._repo.transaction():
                self._repo.clear_all()
                for d in seed_defects():
                    self._repo.save_defect(d)
                for r in seed_lists():
                    self._repo.save_list(r)
            self._scheduler.recover_interrupted()  # 演示数据里有「处理中」的缺陷,要让它真正跑起来
            self._scheduler.remember_transitions()  # 重置后的状态作为新的基线
            await self._scheduler.reconcile()

    # ---------------------------------------------------------------- 内部

    def _spawn(self, coro) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _defects_by_id(self) -> dict[str, Defect]:
        return {d.id: d for d in self._repo.all_defects()}

    def _defects_in(self, record: ListRecord) -> list[Defect]:
        by_id = self._defects_by_id()
        return [by_id[i] for i in record.defect_ids if i in by_id]

    def _state_of(self, record: ListRecord):
        return list_state(record, self._repo.all_lists(), self._defects_by_id())

    def _get_defect(self, defect_id: str) -> Defect:
        defect = self._repo.get_defect(defect_id)
        if defect is None:
            raise NotFound("缺陷不存在")
        return defect

    def _get_review_defect(self, defect_id: str) -> Defect:
        defect = self._get_defect(defect_id)
        if defect.state != "review" or defect.fix is None:
            raise DomainError("只有待审核的缺陷才能这样操作")
        return defect

    def _get_list(self, list_id: str) -> ListRecord:
        record = next((r for r in self._repo.all_lists() if r.id == list_id), None)
        if record is None:
            raise NotFound("清单不存在")
        return record

    def _urgent_list(self) -> ListRecord:
        return next(r for r in self._repo.all_lists() if r.urgent)

    def _next_seq(self) -> int:
        return max((r.seq for r in self._repo.all_lists()), default=0) + 1

    @staticmethod
    def _valid_name(name: str) -> str:
        name = name.strip()
        if not name:
            raise DomainError("请先给清单起个名字")
        return name

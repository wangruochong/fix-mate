"""通知:既记入通知列表,也弹出右上角提示。"""

from collections.abc import Callable
from datetime import datetime

from fix_mate.domain.models import AppNotification, NotificationKind, ToastEvent
from fix_mate.services.events import EventBus
from fix_mate.store.repository import Repository


class Notifier:
    def __init__(self, repo: Repository, bus: EventBus, clock: Callable[[], datetime]):
        self._repo = repo
        self._bus = bus
        self._clock = clock

    def notify(
        self,
        title: str,
        body: str,
        kind: NotificationKind,
        defect_id: str | None = None,
        *,
        quiet: bool = False,
    ) -> None:
        """quiet 为真时只弹提示,不进入通知列表(用于用户自己操作的确认反馈)。"""
        if not quiet:
            n = self._repo.next_counter("notification")
            self._repo.add_notification(
                AppNotification(
                    id=f"N-{n}",
                    title=title,
                    body=body,
                    kind=kind,
                    defect_id=defect_id,
                    unread=True,
                    created_at=self._clock(),
                )
            )
        self._bus.publish(ToastEvent(title=title, body=body, kind=kind, defect_id=defect_id, quiet=quiet))

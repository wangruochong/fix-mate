"""领域模型,同时也是对外接口的数据结构。

和前端 `web/src/types/` 一一对应:字段名在 JSON 里是 camelCase(靠别名),Python 里是 snake_case。
对外序列化时统一**去掉值为 None 的字段**,对应 TypeScript 里的可选字段(不存在,而不是 null)。
`tests/test_contract.py` 会检查这里的字段和前端类型没有跑偏。
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    """所有对外模型的基类:JSON 用 camelCase,代码里两种写法都能构造。"""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    def to_json(self) -> dict:
        """转成可直接 JSON 序列化的字典:camelCase,且去掉 None 字段。"""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


# ---------------------------------------------------------------- 缺陷

DefectState = Literal[
    "queued",  # 排队中
    "analyzing",  # AI 处理中
    "paused",  # 已暂停
    "review",  # 待审核
    "accepted",  # 已接受(终态)
    "rejected",  # 已拒绝(终态)
    "passed",  # 已跳过(终态)
]
DefectType = Literal["Bug", "建议", "测试需求", "历史遗留问题"]
Priority = Literal["Blocker", "Critical", "Major", "Minor"]

#: AI 视角下「未处理完」的状态
UNDONE_STATES: frozenset[str] = frozenset({"queued", "analyzing", "paused"})


class CodeSegment(ApiModel):
    code: str


class BoldSegment(ApiModel):
    bold: str


#: 行内富文本片段:普通文字、代码、加粗。前端用结构化数据渲染,不使用 HTML。
RichSegment = str | CodeSegment | BoldSegment
RichText = list[RichSegment]


class DiffLine(ApiModel):
    kind: Literal["hunk", "ctx", "add", "del"]
    text: str


class FixFile(ApiModel):
    name: str
    additions: int
    deletions: int
    lines: list[DiffLine]


class FixConflict(ApiModel):
    """与另一个缺陷修改了同一文件。"""

    # `with` 是 Python 关键字,字段改名,JSON 里仍叫 with
    with_: str = Field(alias="with")
    file: str
    range: str


class Fix(ApiModel):
    """AI 生成的修复方案。"""

    confidence: int
    branch: str
    commit: str
    judge: str
    summary: list[RichText]
    conclusion: RichText
    files: list[FixFile]
    conflicts: list[FixConflict]
    #: 复核后写入的结果说明
    recheck: str | None = None


class CachedConclusion(ApiModel):
    """修复时缓存的结论摘要,复核时使用。"""

    at: datetime
    base_commit: str
    text: str


PauseCause = Literal[
    "user",  # 用户手动暂停,需要手动继续
    "preempted",  # 被插队打断,会自动恢复
]


class PauseInfo(ApiModel):
    cause: PauseCause
    at: datetime
    #: 已有的中间结果
    note: str | None = None
    #: 暂停前 AI 判断出的置信度(已完成判断时才有)
    confidence: int | None = None


class Accepted(ApiModel):
    kind: Literal["accepted"] = "accepted"
    ota: str
    commit: str


class Rejected(ApiModel):
    kind: Literal["rejected"] = "rejected"
    keep_changes: bool
    reason: str | None = None


class Passed(ApiModel):
    kind: Literal["passed"] = "passed"
    auto: bool
    reason: str


#: 终态缺陷的处理结果
Outcome = Annotated[Accepted | Rejected | Passed, Field(discriminator="kind")]


class AcceptError(ApiModel):
    """接受流程卡在了哪一步。缺陷仍是「待审核」,用户再点接受会从这一步继续,已完成的步骤不会重做。"""

    #: 失败的步骤,从 0 开始(共 7 步)
    step: int
    message: str


class Defect(ApiModel):
    id: str
    title: str
    type: DefectType
    priority: Priority
    requirement: str
    version: str
    reporter: str
    created_at: datetime
    description: str
    state: DefectState
    #: analyzing / paused 时所处的步骤,从 0 开始
    step: int | None = None
    pause: PauseInfo | None = None
    #: 被插队打断后恢复时,已把临时分支同步到最新 main
    rebased: bool | None = None
    #: 正在复核
    rechecking: bool | None = None
    fix: Fix | None = None
    #: 待审核时,是否需要复核
    needs_recheck: bool | None = None
    cached: CachedConclusion | None = None
    #: 待审核时,上一次接受失败的原因
    accept_error: AcceptError | None = None
    #: accepted / rejected / passed 时的处理结果
    outcome: Outcome | None = None

    @property
    def is_undone(self) -> bool:
        return self.state in UNDONE_STATES


class AcceptRecord(BaseModel):
    """接受流程的进度,只存在业务库里(不对外)。接受流程做到哪了,以它为准。

    接受包含 push 和打包这类不可撤销的动作,所以每一步都要在做之前记下「开始了」,做完记下「完成了」。
    """

    #: 已经完成的步骤数(0 到 7)
    done: int = 0
    #: 已经开始、但还没记录完成的步骤。它不为空说明上次在这一步中断了(失败或崩溃),不知道有没有生效
    running: int | None = None
    #: 用户已经确认过「上次中断的这一步可以重做」
    acknowledged: bool = False
    #: 把修复放进 main 后,main 上新的提交号
    picked_commit: str | None = None
    #: 推送之后 main 的提交号
    pushed_commit: str | None = None
    ota: str | None = None


# ---------------------------------------------------------------- 清单

ListState = Literal[
    "pending",  # 待处理:没开始过,或被用户暂停,且还有未处理完的缺陷
    "queued",  # 排队中:用户已点过,前面还有别的清单
    "running",  # 处理中
    "done",  # 处理完成:没有未处理完的缺陷
]


class ListRecord(BaseModel):
    """清单的存储形式。`on` 和 `seq` 是调度的输入,界面看到的状态由它们和缺陷状态推导。"""

    id: str
    name: str
    urgent: bool = False
    created_at: datetime
    #: 用户已点开始且没暂停
    on: bool = False
    #: 排队顺序,越小越靠前
    seq: int = 0
    defect_ids: list[str] = []


class DefectList(ApiModel):
    id: str
    name: str
    urgent: bool | None = None
    created_at: datetime
    defect_ids: list[str]
    #: 由缺陷状态推导,不单独存储
    state: ListState


# ---------------------------------------------------------------- 通知与事件

NotificationKind = Literal["new", "ok", "skip", "done", "warn"]


class AppNotification(ApiModel):
    id: str
    title: str
    body: str
    kind: NotificationKind
    defect_id: str | None = None
    unread: bool
    created_at: datetime


class ChangedEvent(ApiModel):
    """数据变了,前端重新获取。"""

    type: Literal["changed"] = "changed"


class ToastEvent(ApiModel):
    type: Literal["toast"] = "toast"
    title: str
    body: str
    kind: NotificationKind
    defect_id: str | None = None
    quiet: bool


class AcceptProgressEvent(ApiModel):
    """接受流程的进度。step 为已完成的步骤数(0 到 7)。"""

    type: Literal["accept-progress"] = "accept-progress"
    defect_id: str
    step: int
    ota: str | None = None
    #: 流程在 step 这一步失败,值是原因
    error: str | None = None


ServerEvent = ChangedEvent | ToastEvent | AcceptProgressEvent

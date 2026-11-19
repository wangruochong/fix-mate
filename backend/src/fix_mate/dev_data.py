"""开发调试用:批量生成随机缺陷,测试大量缺陷时的列表、搜索表现。"""

import random
from datetime import UTC, datetime, timedelta

from fix_mate.domain.models import Accepted, Defect, DefectState, Passed, PauseInfo, Rejected

_REQUIREMENTS = ["账号体系改版", "个人中心 2.0", "报表中心", "消息中心重构", "设置页重构", "支付链路优化"]
_VERSIONS = ["v3.8.0", "v3.7.2", "v3.7.1", "v3.6.5"]
_SUBJECTS = [
    "登录页",
    "订单列表",
    "个人中心",
    "报表导出",
    "消息推送",
    "设置页",
    "支付回调",
    "搜索结果",
    "启动页",
    "头像上传",
]
_PROBLEMS = [
    "偶现白屏",
    "点击无响应",
    "显示错位",
    "提示信息不准确",
    "加载很慢",
    "数据不同步",
    "闪退",
    "文案有误",
    "动画卡顿",
]
_TYPES = ["Bug", "建议", "测试需求", "历史遗留问题"]
_PRIORITIES = ["Blocker", "Critical", "Major", "Minor"]
_SURNAMES = ["王", "李", "张", "刘", "陈", "杨", "赵", "黄", "周", "吴"]
#: 状态占比:大部分在排队,少量已处理,贴近真实使用时的分布
_STATE_WEIGHTS: list[tuple[DefectState, int]] = [
    ("queued", 70), ("accepted", 12), ("rejected", 6), ("passed", 8), ("paused", 4),
]  # fmt: skip


def fake_defects(n: int, start_id: int = 5000, rng: random.Random | None = None) -> list[Defect]:
    rng = rng or random.Random()
    states, weights = zip(*_STATE_WEIGHTS, strict=True)
    now = datetime.now(UTC)
    result = []
    for i in range(n):
        type_ = rng.choice(_TYPES)
        state: DefectState = rng.choices(states, weights)[0]
        d = Defect(
            id=f"{'SUG' if type_ == '建议' else 'BUG'}-{start_id + i}",
            title=f"{rng.choice(_SUBJECTS)}{rng.choice(_PROBLEMS)}",
            type=type_,  # type: ignore[arg-type]
            priority=rng.choice(_PRIORITIES),  # type: ignore[arg-type]
            requirement=rng.choice(_REQUIREMENTS),
            version=rng.choice(_VERSIONS),
            reporter=rng.choice(_SURNAMES) + rng.choice(["明", "芳", "伟", "静", "强"]),
            created_at=now - timedelta(minutes=rng.randrange(60 * 24 * 30)),
            description="这是批量生成的测试缺陷。",
            state=state,
        )
        if state == "accepted":
            d.outcome = Accepted(ota=f"3.7.2.{rng.randrange(2000, 2400)}", commit=f"{rng.randrange(16**7):07x}")
        elif state == "rejected":
            d.outcome = Rejected(keep_changes=rng.random() < 0.5)
        elif state == "passed":
            d.outcome = Passed(auto=False, reason="需求描述不明确,需先和产品确认。")
        elif state == "paused":
            d.step = 2
            d.pause = PauseInfo(cause="user", at=now)
        result.append(d)
    return result

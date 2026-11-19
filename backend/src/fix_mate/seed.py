"""开发和演示用的种子数据,与前端 `web/src/mock/seed.ts` 保持一致,方便前后端对照。"""

from datetime import UTC, datetime, timedelta

from fix_mate.domain.models import (
    Accepted,
    BoldSegment,
    CachedConclusion,
    CodeSegment,
    Defect,
    DiffLine,
    Fix,
    FixConflict,
    FixFile,
    ListRecord,
    Passed,
    PauseInfo,
    Rejected,
)

LONG_REQ = "支付链路优化 · 海外多币种结算与风控联动改造(二期)"
LONG_VER = "v3.8.0 · 2026Q4 国际版灰度发布(含 Android / iOS 双端同步上线)"


def _ago(minutes: float) -> datetime:
    return datetime.now(UTC) - timedelta(minutes=minutes)


def _hours(h: float) -> float:
    return h * 60


def _days(d: float) -> float:
    return d * 24 * 60


def _line(kind: str, text: str) -> DiffLine:
    return DiffLine(kind=kind, text=text)  # type: ignore[arg-type]


def seed_defects() -> list[Defect]:
    return [
        Defect(
            id="BUG-2481",
            title="登录页点击「忘记密码」无响应",
            type="Bug",
            priority="Critical",
            requirement="账号体系改版",
            version="v3.8.0",
            reporter="李晓雯",
            created_at=_ago(10),
            description="在登录页点击「忘记密码」链接,没有任何反应,也无报错。复现:冷启动 App → 登录页 → 点击链接。Android / iOS 均可复现。",
            state="review",
            fix=Fix(
                confidence=92,
                branch="fixmate/BUG-2481",
                commit="e4b7a90",
                judge="问题定位明确:链接的点击回调只更新了本地状态,没有触发路由跳转,属于可通过修改代码解决的确定性问题。",
                summary=[
                    ["为「忘记密码」补上路由跳转 ", CodeSegment(code="navigate('/reset')")],
                    ["在 AuthService 新增 ", CodeSegment(code="validateCredential()"), ",统一校验账号格式"],
                    ["补充 2 个单元测试"],
                ],
                conclusion=[
                    "根因是 ",
                    BoldSegment(bold="onForgot"),
                    " 被误写成只 setState;已在 LoginView 修复。AuthService 里新增的校验函数后续可被其它登录类缺陷复用。",
                ],
                files=[
                    FixFile(
                        name="src/pages/Login/LoginView.tsx",
                        additions=6,
                        deletions=2,
                        lines=[
                            _line("hunk", "@@ -38,8 +38,12 @@"),
                            _line("ctx", "  const onForgot = () => {"),
                            _line("del", "-   setShowTip(true)"),
                            _line("add", "+   track('forgot_click')"),
                            _line("add", "+   navigate('/reset', { from: 'login' })"),
                            _line("ctx", "  }"),
                        ],
                    ),
                    FixFile(
                        name="src/services/AuthService.ts",
                        additions=11,
                        deletions=1,
                        lines=[
                            _line("hunk", "@@ -40,6 +40,16 @@"),
                            _line("add", "+ export function validateCredential(v: string) {"),
                            _line("add", "+   if (!v) return { ok: false, reason: 'EMPTY' }"),
                            _line("add", "+   return { ok: EMAIL.test(v) || PHONE.test(v) }"),
                            _line("add", "+ }"),
                            _line("del", "- const ok = v.length > 0"),
                            _line("add", "+ const ok = validateCredential(v).ok"),
                        ],
                    ),
                ],
                conflicts=[],
            ),
        ),
        Defect(
            id="BUG-2462",
            title="登录失败时提示信息不准确",
            type="Bug",
            priority="Major",
            requirement="账号体系改版",
            version="v3.8.0",
            reporter="陈子墨",
            created_at=_ago(32),
            description="密码错误与账号不存在时,都提示「网络异常,请重试」,用户无法判断真实原因。",
            state="review",
            needs_recheck=True,
            cached=CachedConclusion(
                at=_ago(25),
                base_commit="a3f9c21",
                text="错误码已在 AuthService.login() 返回,但 UI 层统一吞掉并展示通用文案。方案:按错误码映射文案。注意该函数与账号校验逻辑相邻,可能被其它缺陷改动。",
            ),
            fix=Fix(
                confidence=88,
                branch="fixmate/BUG-2462",
                commit="7c1d3be",
                judge="错误码已存在,仅需在 UI 层做映射,属于确定性问题。",
                summary=[["新增错误码到文案的映射表"], ["登录失败时展示对应提示"], ["补充 3 条文案用例"]],
                conclusion=["基于缓存结论:UI 层吞掉了错误码。"],
                files=[
                    FixFile(
                        name="src/services/AuthService.ts",
                        additions=14,
                        deletions=4,
                        lines=[
                            _line("hunk", "@@ -42,16 +42,26 @@"),
                            _line("del", "-   throw new Error('NETWORK')"),
                            _line("add", "+   throw new AuthError(code, ERR_TEXT[code])"),
                        ],
                    )
                ],
                conflicts=[FixConflict(with_="BUG-2481", file="src/services/AuthService.ts", range="42–58")],
            ),
        ),
        Defect(
            id="BUG-2476",
            title="弱网下订单提交可能重复扣款",
            type="Bug",
            priority="Blocker",
            requirement=LONG_REQ,
            version=LONG_VER,
            reporter="赵一鸣",
            created_at=_ago(_hours(1)),
            description="弱网环境下连续点击提交,订单接口超时重试,偶发创建两笔订单并重复扣款。",
            state="analyzing",
            step=1,
        ),
        Defect(
            id="BUG-2469",
            title="个人中心头像裁剪后显示被拉伸",
            type="Bug",
            priority="Major",
            requirement="个人中心 2.0",
            version="v3.7.2",
            reporter="周楠",
            created_at=_ago(_hours(2)),
            description="裁剪非正方形区域后上传,头像在个人中心被拉伸变形。",
            state="queued",
        ),
        Defect(
            id="SUG-1120",
            title="希望设置页支持深色模式手动切换",
            type="建议",
            priority="Minor",
            requirement="设置页重构",
            version="v3.8.0",
            reporter="吴珊",
            created_at=_ago(_hours(3)),
            description="目前深色模式只能跟随系统,希望可以手动切换。",
            state="queued",
        ),
        Defect(
            id="TST-0933",
            title="补充登录模块的单元测试",
            type="测试需求",
            priority="Major",
            requirement="账号体系改版",
            version="v3.8.0",
            reporter="孙浩",
            created_at=_ago(_hours(26)),
            description="登录模块当前单测覆盖率偏低,需补充异常分支用例。",
            state="paused",
            step=2,
            pause=PauseInfo(
                cause="user",
                at=_ago(_hours(20)),
                confidence=90,
                note="已定位到登录模块的 5 个异常分支,完成了其中 3 个用例的编写",
            ),
        ),
        Defect(
            id="BUG-2455",
            title="旧版报表导出中文乱码",
            type="历史遗留问题",
            priority="Critical",
            requirement="报表中心",
            version="v3.7.2",
            reporter="李晓雯",
            created_at=_ago(_hours(27)),
            description="老版本导出的 CSV 在 Excel 中打开出现中文乱码。",
            state="accepted",
            outcome=Accepted(ota="3.7.2.2398", commit="b82f4e1"),
        ),
        Defect(
            id="BUG-2450",
            title="消息列表快速滚动时掉帧",
            type="Bug",
            priority="Major",
            requirement="消息中心重构",
            version="v3.7.1",
            reporter="陈子墨",
            created_at=_ago(_hours(28)),
            description="消息超过 500 条后快速滚动明显掉帧。",
            state="rejected",
            outcome=Rejected(keep_changes=True, reason="思路对但改动范围偏大,保留代码自己再调整"),
        ),
        Defect(
            id="SUG-1103",
            title="反馈入口文案不够明确",
            type="建议",
            priority="Minor",
            requirement="设置页重构",
            version="v3.7.1",
            reporter="吴珊",
            created_at=_ago(_days(2)),
            description="「意见反馈」入口希望文案更明确。",
            state="passed",
            outcome=Passed(auto=False, reason="需求描述不明确,需先和产品确认文案。"),
        ),
        Defect(
            id="BUG-2431",
            title="设置页开关切换动画卡顿",
            type="Bug",
            priority="Minor",
            requirement="设置页重构",
            version="v3.7.2",
            reporter="周楠",
            created_at=_ago(_days(3)),
            description="设置页的开关切换时动画掉帧,低端机尤为明显。",
            state="queued",
        ),
        Defect(
            id="BUG-2438",
            title="夜间模式下图表坐标轴标签看不清",
            type="历史遗留问题",
            priority="Major",
            requirement="报表中心",
            version="v3.7.1",
            reporter="孙浩",
            created_at=_ago(_hours(29)),
            description="夜间模式下报表图表的坐标轴文字颜色与背景接近。",
            state="queued",
        ),
        Defect(
            id="BUG-2420",
            title="支付回调偶发丢失导致订单状态不同步",
            type="Bug",
            priority="Blocker",
            requirement=LONG_REQ,
            version="v3.7.2",
            reporter="赵一鸣",
            created_at=_ago(_days(3)),
            description="支付渠道回调偶发丢失,订单长时间停留在「支付中」。",
            state="queued",
        ),
        Defect(
            id="SUG-1098",
            title="希望订单页支持按时间筛选",
            type="建议",
            priority="Minor",
            requirement=LONG_REQ,
            version="v3.8.0",
            reporter="吴珊",
            created_at=_ago(_days(4)),
            description="订单较多时希望可以按时间范围筛选。",
            state="queued",
        ),
    ]


def seed_lists() -> list[ListRecord]:
    return [
        ListRecord(id="L-URGENT", name="紧急", urgent=True, created_at=_ago(_days(30)), on=True, seq=0),
        ListRecord(
            id="L-0001",
            name="本周迭代",
            created_at=_ago(_days(10)),
            on=True,
            seq=1,
            defect_ids=["BUG-2455", "BUG-2450", "BUG-2481", "BUG-2462", "BUG-2476", "BUG-2469", "SUG-1120"],
        ),
        ListRecord(
            id="L-0002",
            name="账号体系改版",
            created_at=_ago(_days(11)),
            on=False,
            seq=2,
            defect_ids=["BUG-2481", "BUG-2462", "TST-0933"],
        ),
        ListRecord(
            id="L-0003",
            name="待跟进",
            created_at=_ago(_days(15)),
            on=True,
            seq=3,
            defect_ids=["SUG-1103", "BUG-2450"],
        ),
        ListRecord(id="L-0004", name="待跟进", created_at=_ago(_days(13)), on=False, seq=0, defect_ids=["BUG-2431"]),
    ]

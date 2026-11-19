"""应用工厂:把存储、事件总线、调度器、执行器装配起来,挂上接口。"""

import logging
import shutil
from collections.abc import AsyncIterator, Callable
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from fix_mate.adapters.claude import ClaudeCodeFixer
from fix_mate.adapters.fakes import DevFakes, FakeCodeFixer, FakeFeishu, FakeJenkins
from fix_mate.adapters.git import GitWorkspace
from fix_mate.adapters.sandbox import ensure_sandbox
from fix_mate.api import routes
from fix_mate.api.security import LocalOnlyMiddleware
from fix_mate.config import Settings
from fix_mate.engine.accepter import GraphAccepter
from fix_mate.engine.checkpoints import open_checkpointer
from fix_mate.engine.external import CodeFixer
from fix_mate.engine.ports import Accepter, Rechecker, Runner
from fix_mate.engine.runner import GraphRunner
from fix_mate.engine.stub import PlaceholderRechecker, StubExecutor
from fix_mate.seed import seed_defects, seed_lists
from fix_mate.services.commands import Commands
from fix_mate.services.errors import DomainError
from fix_mate.services.events import EventBus
from fix_mate.services.notifier import Notifier
from fix_mate.services.scheduler import Scheduler
from fix_mate.store.db import open_database
from fix_mate.store.repository import Repository, RepositoryAcceptProgress, RepositorySessions

log = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def _build_graph_engine(
    settings: Settings, repo: Repository, stack: AsyncExitStack
) -> tuple[GraphRunner, GraphAccepter, DevFakes]:
    """装配真正的 AI 引擎:修复(git 工作区 + 改代码 + LangGraph 检查点)和接受(git + Jenkins + 飞书)。"""
    saver = await stack.enter_async_context(open_checkpointer(settings.data_dir / "checkpoints.db"))
    repo_dir = settings.repo_dir
    if repo_dir is None:
        if not settings.dev:
            raise RuntimeError("使用 graph 引擎需要用 FIXMATE_REPO 指定 FixMate 专用的仓库克隆")
        repo_dir = ensure_sandbox(settings.data_dir / "sandbox")  # 开发模式:用自动创建的沙盒仓库
    fixer: CodeFixer
    if settings.fixer == "fake":
        fixer = FakeCodeFixer(speed=settings.stub_speed)
    elif settings.fixer == "claude":
        if shutil.which("claude") is None:
            raise RuntimeError("找不到 Claude Code。请先安装并登录它(命令行里能运行 claude)。")
        fixer = ClaudeCodeFixer(
            model=settings.claude_model,
            assess_budget_usd=settings.claude_assess_budget,
            fix_budget_usd=settings.claude_fix_budget,
            timeout_seconds=settings.claude_timeout,
        )
    else:
        raise RuntimeError(f"不支持的改代码方式:{settings.fixer}")

    def load_defect(defect_id: str):
        defect = repo.get_defect(defect_id)
        if defect is None:
            raise LookupError(f"缺陷不存在:{defect_id}")
        return defect

    workspace = GitWorkspace(repo_dir, settings.worktrees_dir)  # 修复和接受共用,git 操作在里面排队
    runner = GraphRunner(
        fixer=fixer,
        workspace=workspace,
        sessions=RepositorySessions(repo),
        checkpointer=saver,
        load_defect=load_defect,
        repo_dir=repo_dir,
    )
    # 飞书和 Jenkins 还没有真实实现,目前只有假的(只在 dev 模式可用)
    if not settings.dev:
        raise RuntimeError("飞书和 Jenkins 还没有真实实现,graph 引擎目前只能在 dev 模式使用")
    jenkins, feishu = FakeJenkins(delay=1.0 / settings.stub_speed), FakeFeishu()
    accepter = GraphAccepter(
        workspace=workspace, jenkins=jenkins, feishu=feishu, progress=RepositoryAcceptProgress(repo)
    )
    return runner, accepter, DevFakes(jenkins, feishu)


def create_app(
    settings: Settings | None = None,
    *,
    runner: Runner | None = None,
    accepter: Accepter | None = None,
    rechecker: Rechecker | None = None,
    clock: Callable[[], datetime] = _utc_now,
) -> FastAPI:
    settings = settings or Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conn = open_database(settings.data_dir / "fixmate.db")
        repo = Repository(conn)
        if settings.seed and repo.is_empty():
            with repo.transaction():
                for d in seed_defects():
                    repo.save_defect(d)
                for r in seed_lists():
                    repo.save_list(r)

        bus = EventBus()
        notifier = Notifier(repo, bus, clock)
        stack = AsyncExitStack()
        stub = StubExecutor(speed=settings.stub_speed)  # 接受、复核还没换成真实引擎,先用定时器模拟
        active_runner, active_accepter, active_rechecker = runner, accepter, rechecker
        if runner is None and settings.engine == "graph":
            active_runner, graph_accepter, app.state.dev_fakes = await _build_graph_engine(settings, repo, stack)
            active_accepter = accepter or graph_accepter
            # 真实引擎下复核先用占位实现:它不能改动真实的提交号(见 PlaceholderRechecker)
            active_rechecker = rechecker or PlaceholderRechecker(speed=settings.stub_speed)
        scheduler = Scheduler(repo, active_runner or stub, bus, notifier, clock)
        commands = Commands(repo, scheduler, active_accepter or stub, active_rechecker or stub, bus, notifier, clock)
        app.state.bus = bus
        app.state.commands = commands
        app.state.scheduler = scheduler
        await scheduler.start()
        await commands.recover_accepts()
        try:
            yield
        finally:
            await commands.shutdown()
            await scheduler.stop()
            await stack.aclose()
            conn.close()

    app = FastAPI(title="FixMate", lifespan=lifespan)
    app.add_middleware(LocalOnlyMiddleware)
    app.include_router(routes.router)
    if settings.dev:
        app.include_router(routes.dev_router)

    web_root = settings.web_root
    if web_root is not None:  # 最后挂载,让 /api 优先匹配;前端是单页应用,所有页面都是同一个 index.html
        app.mount("/", StaticFiles(directory=web_root, html=True), name="web")

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, e: DomainError) -> JSONResponse:
        return routes.error_response(e.message, e.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, e: RequestValidationError) -> JSONResponse:
        return routes.error_response("请求参数不正确", 422)

    return app

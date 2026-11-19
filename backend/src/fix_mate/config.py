"""运行配置。全部来自环境变量,都有适合本地使用的默认值。"""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    #: 数据目录:业务数据库、检查点库、工作目录都放在这里
    data_dir: Path = Path.home() / ".fixmate"
    #: dev 模式下提供 /api/dev/* 调试接口,并使用假的飞书、Jenkins 和改代码
    dev: bool = False
    #: 启动时数据库为空是否灌入演示数据
    seed: bool = False
    #: 监听地址。只监听本机,不要改成 0.0.0.0
    host: str = "127.0.0.1"
    port: int = 8000
    #: 执行器:graph 是真正的 LangGraph 引擎;stub 是定时器模拟(不碰 git,只用于早期演示和测试)
    engine: str = "graph"
    #: 前端构建产物所在目录。存在时由后端直接提供页面,一个进程就能用
    web_dir: Path | None = None
    #: graph 引擎用的仓库:FixMate 专用的克隆。dev 模式下不设置就用自动创建的沙盒仓库
    repo_dir: Path | None = None
    #: 改代码用谁:fake 是假的(不花钱),claude 是真正的 Claude Code
    fixer: str = "fake"
    #: 真正的 Claude Code 的参数:模型(为空用默认)、判断和改代码各自的费用上限(美元)、整体超时(秒)
    claude_model: str | None = None
    claude_assess_budget: float = 0.5
    claude_fix_budget: float = 3.0
    claude_timeout: float = 1200
    #: 模拟执行器和假改代码的速度倍数,测试里调大让它瞬间完成
    stub_speed: float = 1.0

    @property
    def worktrees_dir(self) -> Path:
        return self.data_dir / "worktrees"

    @property
    def web_root(self) -> Path | None:
        """前端构建产物目录:显式指定的,否则取仓库里的 web/dist(存在才算)。"""
        candidate = self.web_dir or Path(__file__).resolve().parents[3] / "web" / "dist"
        return candidate if (candidate / "index.html").is_file() else None

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        dev = env.get("FIXMATE_ENV", "prod") == "dev"
        return cls(
            data_dir=Path(env.get("FIXMATE_DATA_DIR", str(cls.data_dir))),
            dev=dev,
            seed=env.get("FIXMATE_SEED", "1" if dev else "0") == "1",
            host=env.get("FIXMATE_HOST", cls.host),
            port=int(env.get("FIXMATE_PORT", cls.port)),
            engine=env.get("FIXMATE_ENGINE", cls.engine),
            web_dir=Path(env["FIXMATE_WEB_DIR"]) if "FIXMATE_WEB_DIR" in env else None,
            repo_dir=Path(env["FIXMATE_REPO"]) if "FIXMATE_REPO" in env else None,
            fixer=env.get("FIXMATE_FIXER", "fake"),
            claude_model=env.get("FIXMATE_CLAUDE_MODEL") or None,
            claude_assess_budget=float(env.get("FIXMATE_CLAUDE_ASSESS_BUDGET", cls.claude_assess_budget)),
            claude_fix_budget=float(env.get("FIXMATE_CLAUDE_FIX_BUDGET", cls.claude_fix_budget)),
            claude_timeout=float(env.get("FIXMATE_CLAUDE_TIMEOUT", cls.claude_timeout)),
            stub_speed=float(env.get("FIXMATE_STUB_SPEED", cls.stub_speed)),
        )

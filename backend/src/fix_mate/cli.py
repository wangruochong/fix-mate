"""命令行入口:`uv run fix-mate` 启动服务。"""

import uvicorn

from fix_mate.config import Settings


def main() -> None:
    settings = Settings.from_env()
    where = "前端页面由本服务提供" if settings.web_root else "没有找到前端构建产物(先在 web/ 里运行 npm run build)"
    print(f"FixMate 启动中:http://{settings.host}:{settings.port}  ({where})", flush=True)
    uvicorn.run(
        "fix_mate.api.app:create_app",
        factory=True,
        host=settings.host,
        port=settings.port,
        # 前端用 SSE 长连接,不设超时的话,按 Ctrl+C 后服务会一直等连接关闭而退不出来
        timeout_graceful_shutdown=3,
    )

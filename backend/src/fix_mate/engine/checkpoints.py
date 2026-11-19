"""LangGraph 检查点库的打开方式。

检查点库和业务库是两个独立的文件:检查点写得频繁,分开可以避免和业务数据互相抢写锁。
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver


@asynccontextmanager
async def open_checkpointer(path: Path | str) -> AsyncIterator[AsyncSqliteSaver]:
    """打开检查点库,整个程序运行期间保持打开,退出时关闭。"""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    async with AsyncSqliteSaver.from_conn_string(str(path)) as saver:
        # 必须主动建表:它默认在第一次读写时才建,而我们第一个动作可能是「删除旧检查点」,那时表还不存在
        await saver.setup()
        yield saver

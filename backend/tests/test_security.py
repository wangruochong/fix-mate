"""本地访问保护:只允许本机访问,挡住别的网站和 DNS 重绑定。"""

import httpx
import pytest

from fix_mate.api.app import create_app
from fix_mate.config import Settings
from fix_mate.engine.stub import StubExecutor


@pytest.fixture
async def app(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, dev=True, seed=True), runner=StubExecutor(interval=None))
    async with app.router.lifespan_context(app):
        yield app


async def get(app, url="/api/lists", **headers):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as c:
        return await c.get(url, headers=headers)


@pytest.mark.parametrize("host", ["localhost", "localhost:5173", "127.0.0.1:8000", "[::1]:8000"])
async def test_local_hosts_are_allowed(app, host):
    assert (await get(app, Host=host)).status_code == 200


@pytest.mark.parametrize(
    "host", ["evil.example.com", "evil.example.com:8000", "192.168.1.5:8000", "localhost.evil.com"]
)
async def test_other_hosts_are_rejected(app, host):
    r = await get(app, Host=host)
    assert r.status_code == 403 and r.json() == {"message": "只允许从本机访问"}


@pytest.mark.parametrize("origin", ["http://localhost:5173", "http://127.0.0.1:8000"])
async def test_local_origins_are_allowed(app, origin):
    assert (await get(app, Origin=origin)).status_code == 200


@pytest.mark.parametrize("origin", ["https://evil.example.com", "http://localhost.evil.com", "null"])
async def test_foreign_origins_are_rejected(app, origin):
    assert (await get(app, Origin=origin)).status_code == 403


async def test_requests_without_origin_are_allowed(app):
    assert (await get(app)).status_code == 200  # 命令行工具没有 Origin

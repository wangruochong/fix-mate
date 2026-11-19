"""接口层测试:通过 HTTP 调用,检查状态码、JSON 格式和事件流。"""

import asyncio
import json

import httpx
import pytest

from fix_mate.api import routes
from fix_mate.api.app import create_app
from fix_mate.config import Settings
from fix_mate.engine.stub import StubExecutor


@pytest.fixture
async def client(tmp_path):
    settings = Settings(data_dir=tmp_path, dev=True, seed=True)
    app = create_app(settings, runner=StubExecutor(interval=None, speed=1000, seed=1))
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
            c.app = app  # type: ignore[attr-defined]
            yield c


async def test_defects_are_returned_with_camel_case_and_without_nulls(client):
    data = (await client.get("/api/defects")).json()
    assert len(data) == 13
    review = next(d for d in data if d["id"] == "BUG-2481")
    assert review["createdAt"] and review["fix"]["files"][0]["additions"] == 6
    assert "pause" not in review and None not in review.values()
    conflict = next(d for d in data if d["id"] == "BUG-2462")["fix"]["conflicts"][0]
    assert conflict["with"] == "BUG-2481"  # `with` 是 Python 关键字,JSON 里仍叫 with
    # 富文本是结构化的
    assert {"code": "navigate('/reset')"} in review["fix"]["summary"][0]


async def test_lists_carry_derived_state_and_urgent_comes_first(client):
    lists = (await client.get("/api/lists")).json()
    assert lists[0]["id"] == "L-URGENT"
    assert {x["id"]: x["state"] for x in lists} == {
        "L-URGENT": "pending", "L-0001": "running", "L-0002": "pending", "L-0003": "done", "L-0004": "pending",
    }  # fmt: skip
    assert lists[0]["urgent"] is True and "urgent" not in lists[1]


async def test_unknown_defect_is_404_with_a_chinese_message(client):
    r = await client.get("/api/defects/NOPE")
    assert r.status_code == 404 and r.json() == {"message": "缺陷不存在"}


async def test_domain_errors_become_400_with_the_message(client):
    r = await client.delete("/api/lists/L-URGENT")
    assert r.status_code == 400 and r.json()["message"] == "紧急清单不能删除"


async def test_invalid_body_is_422(client):
    r = await client.post("/api/lists", json={"name": "x"})
    assert r.status_code == 422 and r.json() == {"message": "请求参数不正确"}


async def test_pause_a_list(client):
    assert (await client.post("/api/lists/L-0001/pause")).json() == {"ok": True}
    states = {x["id"]: x["state"] for x in (await client.get("/api/lists")).json()}
    assert states["L-0001"] == "pending"


async def test_create_list_returns_its_id_and_accepts_camel_case_body(client):
    r = await client.post("/api/lists", json={"name": "测试", "defectIds": ["BUG-2431"]})
    assert r.json() == {"id": "L-0005"}
    assert any(x["id"] == "L-0005" for x in (await client.get("/api/lists")).json())


async def test_reject_with_keep_changes(client):
    r = await client.post("/api/defects/BUG-2481/reject", json={"keepChanges": True, "reason": "太大"})
    assert r.status_code == 200
    d = (await client.get("/api/defects/BUG-2481")).json()
    assert d["outcome"] == {"kind": "rejected", "keepChanges": True, "reason": "太大"}


async def test_urgent_position_is_validated(client):
    r = await client.post("/api/defects/BUG-2438/urgent", json={"position": "middle"})
    assert r.status_code == 422


async def test_notifications_and_read(client):
    await client.post("/api/dev/new-defect")
    notes = (await client.get("/api/notifications")).json()
    assert notes[0]["unread"] is True and notes[0]["defectId"].startswith("BUG-")
    await client.post("/api/notifications/read")
    assert all(not n["unread"] for n in (await client.get("/api/notifications")).json())


async def test_dev_endpoints_bulk_and_reset(client):
    await client.post("/api/dev/bulk", json={"count": 300})
    defects = (await client.get("/api/defects")).json()
    assert len(defects) == 313 and len({d["id"] for d in defects}) == 313
    await client.post("/api/dev/reset")
    assert len((await client.get("/api/defects")).json()) == 13


async def test_dev_endpoints_are_absent_outside_dev_mode(tmp_path):
    app = create_app(Settings(data_dir=tmp_path, dev=False, seed=True), runner=StubExecutor(interval=None))
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://localhost") as c,
    ):
        assert (await c.post("/api/dev/reset")).status_code in (404, 405)


async def test_event_stream_delivers_toast_and_changed_events(client):
    bus = client.app.state.bus
    response = await routes.events(None, bus)  # 直接取事件流的生成器(httpx 的内存传输不支持流式响应)
    stream = response.body_iterator
    assert (await anext(stream)).startswith(": connected")
    await client.post("/api/lists/L-0001/pause")
    events = []
    while {"type": "changed"} not in events:  # 提示立即到,「数据变了」会合并后稍晚到
        chunk = await asyncio.wait_for(anext(stream), 2)
        if chunk.startswith("data: "):
            events.append(json.loads(chunk.removeprefix("data: ")))
    toast = next(e for e in events if e["type"] == "toast")
    assert toast["title"] == "已暂停「本周迭代」"
    assert toast["kind"] == "skip" and toast["quiet"] is True
    await stream.aclose()


async def test_data_survives_a_restart_and_seed_is_not_applied_twice(tmp_path):
    settings = Settings(data_dir=tmp_path, dev=True, seed=True)

    async def session(do):
        app = create_app(settings, runner=StubExecutor(interval=None, speed=1000))
        transport = httpx.ASGITransport(app=app)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(transport=transport, base_url="http://localhost") as c,
        ):
            return await do(c)

    async def create(c):
        await c.post("/api/lists", json={"name": "重启测试", "defectIds": []})

    async def read(c):
        lists = (await c.get("/api/lists")).json()
        return [x["name"] for x in lists], len((await c.get("/api/defects")).json())

    await session(create)
    names, defect_count = await session(read)
    assert "重启测试" in names
    assert defect_count == 13  # 没有因为重启再灌一遍演示数据


async def test_built_frontend_is_served_by_the_backend(tmp_path):
    web = tmp_path / "dist"
    web.mkdir()
    (web / "index.html").write_text("<html>FixMate 页面</html>")
    settings = Settings(data_dir=tmp_path / "data", dev=True, seed=True, web_dir=web)
    app = create_app(settings, runner=StubExecutor(interval=None))
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://localhost") as c,
    ):
        page = await c.get("/")
        assert page.status_code == 200 and "FixMate 页面" in page.text
        assert (await c.get("/api/lists")).status_code == 200  # 接口不受静态文件影响


async def test_without_a_build_the_root_is_not_found(tmp_path):
    settings = Settings(data_dir=tmp_path / "data", dev=True, seed=True, web_dir=tmp_path / "missing")
    app = create_app(settings, runner=StubExecutor(interval=None))
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://localhost") as c,
    ):
        assert (await c.get("/")).status_code == 404

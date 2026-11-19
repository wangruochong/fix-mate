"""REST 接口和事件流。接口表见 web/README.md。

接口层很薄:校验请求、调用 `Commands`、把结果转成 JSON。业务规则不在这里。
响应统一用 `to_json()`:camelCase,并且不输出值为 None 的字段。
"""

import asyncio
import json
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from fix_mate.domain.models import ApiModel
from fix_mate.services.commands import Commands
from fix_mate.services.errors import DomainError
from fix_mate.services.events import EventBus


def get_commands(request: Request) -> Commands:
    return request.app.state.commands


def get_bus(request: Request) -> EventBus:
    return request.app.state.bus


CommandsDep = Annotated[Commands, Depends(get_commands)]
BusDep = Annotated[EventBus, Depends(get_bus)]

router = APIRouter(prefix="/api")
OK = {"ok": True}


# ---------------------------------------------------------------- 请求体


class ListInput(ApiModel):
    name: str
    defect_ids: list[str]


class DefectIdInput(ApiModel):
    defect_id: str


class UrgentInput(ApiModel):
    position: Literal["front", "back"]


class RejectInput(ApiModel):
    keep_changes: bool
    reason: str | None = None


class PassInput(ApiModel):
    reason: str


class BulkInput(BaseModel):
    count: int = Field(ge=1, le=1000)


class FailStepInput(BaseModel):
    step: int | None = None


# ---------------------------------------------------------------- 查询


@router.get("/defects")
async def list_defects(commands: CommandsDep):
    return [d.to_json() for d in commands.defects()]


@router.get("/defects/{defect_id}")
async def get_defect(defect_id: str, commands: CommandsDep):
    return commands.defect(defect_id).to_json()


@router.get("/lists")
async def list_lists(commands: CommandsDep):
    return [x.to_json() for x in commands.lists()]


@router.get("/notifications")
async def list_notifications(commands: CommandsDep):
    return [n.to_json() for n in commands.notifications()]


@router.post("/notifications/read")
async def read_notifications(commands: CommandsDep):
    await commands.mark_notifications_read()
    return OK


# ---------------------------------------------------------------- 清单


@router.post("/lists")
async def create_list(body: ListInput, commands: CommandsDep):
    return {"id": await commands.create_list(body.name, body.defect_ids)}


@router.patch("/lists/{list_id}")
async def update_list(list_id: str, body: ListInput, commands: CommandsDep):
    await commands.update_list(list_id, body.name, body.defect_ids)
    return OK


@router.delete("/lists/{list_id}")
async def delete_list(list_id: str, commands: CommandsDep):
    await commands.delete_list(list_id)
    return OK


@router.post("/lists/{list_id}/start")
async def start_list(list_id: str, commands: CommandsDep):
    await commands.start_list(list_id)
    return OK


@router.post("/lists/{list_id}/pause")
async def pause_list(list_id: str, commands: CommandsDep):
    await commands.pause_list(list_id)
    return OK


@router.post("/lists/{list_id}/prioritize")
async def prioritize_list(list_id: str, commands: CommandsDep):
    await commands.prioritize_list(list_id)
    return OK


@router.post("/lists/{list_id}/defects")
async def add_to_list(list_id: str, body: DefectIdInput, commands: CommandsDep):
    await commands.add_to_list(list_id, body.defect_id)
    return OK


@router.delete("/lists/{list_id}/defects/{defect_id}")
async def remove_from_list(list_id: str, defect_id: str, commands: CommandsDep):
    await commands.remove_from_list(list_id, defect_id)
    return OK


# ---------------------------------------------------------------- 缺陷操作


@router.post("/defects/{defect_id}/pause")
async def pause_defect(defect_id: str, commands: CommandsDep):
    await commands.pause_defect(defect_id)
    return OK


@router.post("/defects/{defect_id}/resume")
async def resume_defect(defect_id: str, commands: CommandsDep):
    await commands.resume_defect(defect_id)
    return OK


@router.post("/defects/{defect_id}/urgent")
async def set_urgent(defect_id: str, body: UrgentInput, commands: CommandsDep):
    await commands.set_urgent(defect_id, body.position)
    return OK


@router.post("/defects/{defect_id}/recheck")
async def recheck(defect_id: str, commands: CommandsDep):
    await commands.recheck(defect_id)
    return OK


@router.post("/defects/{defect_id}/accept")
async def accept(defect_id: str, commands: CommandsDep):
    await commands.accept(defect_id)
    return OK


@router.post("/defects/{defect_id}/reject")
async def reject(defect_id: str, body: RejectInput, commands: CommandsDep):
    await commands.reject(defect_id, body.keep_changes, body.reason)
    return OK


@router.post("/defects/{defect_id}/pass")
async def pass_defect(defect_id: str, body: PassInput, commands: CommandsDep):
    await commands.pass_(defect_id, body.reason)
    return OK


# ---------------------------------------------------------------- 事件流

KEEPALIVE_SECONDS = 15


@router.get("/events")
async def events(request: Request, bus: BusDep):
    """SSE 事件流。事件类型见 domain/models.py 的 ServerEvent。"""
    queue = bus.subscribe()

    async def stream():
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), KEEPALIVE_SECONDS)
                except TimeoutError:
                    yield ": keepalive\n\n"  # 防止中间的代理断开空闲连接
                    continue
                yield f"data: {json.dumps(event.to_json(), ensure_ascii=False)}\n\n"
        finally:
            bus.unsubscribe(queue)

    return StreamingResponse(
        stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


# ---------------------------------------------------------------- 开发调试(仅 dev 模式挂载)

dev_router = APIRouter(prefix="/api/dev")


@dev_router.post("/new-defect")
async def dev_new_defect(commands: CommandsDep):
    return (await commands.simulate_new_defect()).to_json()


@dev_router.post("/bulk")
async def dev_bulk(body: BulkInput, commands: CommandsDep):
    from fix_mate.dev_data import fake_defects

    await commands.add_defects(fake_defects(body.count))
    return OK


@dev_router.post("/accept-failure")
async def dev_accept_failure(body: FailStepInput, request: Request):
    """让接受流程的某一步失败(只有 graph 引擎的开发模式支持)。step 为空表示恢复正常。"""
    fakes = getattr(request.app.state, "dev_fakes", None)
    if fakes is None:
        raise DomainError("只有使用 graph 引擎的开发模式才能注入故障")
    fakes.fail_step(body.step)
    return OK


@dev_router.post("/reset")
async def dev_reset(commands: CommandsDep):
    await commands.reset()
    return OK


def error_response(message: str, status: int) -> JSONResponse:
    return JSONResponse({"message": message}, status_code=status)

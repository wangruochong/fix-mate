import { delay, http, HttpResponse, sse } from 'msw'
import { fakeDefects } from './bulk'
import { engine } from './engine'

/** 模拟网络延迟,让加载状态也能被看到。 */
const LATENCY = 120

const ok = () => HttpResponse.json({ ok: true })
const notFound = (message: string) => HttpResponse.json({ message }, { status: 404 })

/** 先延迟,再执行,把引擎抛出的错误转成 400。 */
async function run(fn: () => unknown) {
  await delay(LATENCY)
  try {
    const result = fn()
    return result === undefined ? ok() : HttpResponse.json(result)
  } catch (e) {
    return HttpResponse.json({ message: e instanceof Error ? e.message : '操作失败' }, { status: 400 })
  }
}

export const handlers = [
  /* 查询 */
  http.get('*/api/defects', async () => {
    await delay(LATENCY)
    return HttpResponse.json(engine.getDefects())
  }),
  http.get('*/api/defects/:id', async ({ params }) => {
    await delay(LATENCY)
    const defect = engine.getDefects().find((d) => d.id === params.id)
    return defect ? HttpResponse.json(defect) : notFound('缺陷不存在')
  }),
  http.get('*/api/lists', async () => {
    await delay(LATENCY)
    return HttpResponse.json(engine.getLists())
  }),
  http.get('*/api/notifications', async () => {
    await delay(LATENCY)
    return HttpResponse.json(engine.getNotifications())
  }),
  http.post('*/api/notifications/read', () => run(() => engine.markAllRead())),

  /* 清单 */
  http.post('*/api/lists', async ({ request }) => {
    const body = (await request.json()) as { name: string; defectIds: string[] }
    return run(() => ({ id: engine.createList(body) }))
  }),
  http.patch('*/api/lists/:id', async ({ params, request }) => {
    const body = (await request.json()) as { name: string; defectIds: string[] }
    return run(() => engine.updateList(String(params.id), body))
  }),
  http.delete('*/api/lists/:id', ({ params }) => run(() => engine.deleteList(String(params.id)))),
  http.post('*/api/lists/:id/start', ({ params }) => run(() => engine.startList(String(params.id)))),
  http.post('*/api/lists/:id/pause', ({ params }) => run(() => engine.pauseList(String(params.id)))),
  http.post('*/api/lists/:id/prioritize', ({ params }) => run(() => engine.jumpList(String(params.id)))),
  http.post('*/api/lists/:id/defects', async ({ params, request }) => {
    const body = (await request.json()) as { defectId: string }
    return run(() => engine.addToList(String(params.id), body.defectId))
  }),
  http.delete('*/api/lists/:id/defects/:defectId', ({ params }) =>
    run(() => engine.removeFromList(String(params.id), String(params.defectId))),
  ),

  /* 缺陷操作 */
  http.post('*/api/defects/:id/pause', ({ params }) => run(() => engine.pauseDefect(String(params.id)))),
  http.post('*/api/defects/:id/resume', ({ params }) => run(() => engine.resumeDefect(String(params.id)))),
  http.post('*/api/defects/:id/urgent', async ({ params, request }) => {
    const body = (await request.json()) as { position: 'front' | 'back' }
    return run(() => engine.addUrgent(String(params.id), body.position))
  }),
  http.post('*/api/defects/:id/recheck', ({ params }) => run(() => engine.recheck(String(params.id)))),
  http.post('*/api/defects/:id/accept', ({ params }) => run(() => engine.accept(String(params.id)))),
  http.post('*/api/defects/:id/reject', async ({ params, request }) => {
    const body = (await request.json()) as { keepChanges: boolean; reason?: string }
    return run(() => engine.reject(String(params.id), body))
  }),
  http.post('*/api/defects/:id/pass', async ({ params, request }) => {
    const body = (await request.json()) as { reason: string }
    return run(() => engine.pass(String(params.id), body.reason))
  }),

  /* 开发调试,只存在于假接口里 */
  http.post('*/api/dev/new-defect', () => run(() => engine.simulateNewDefect())),
  http.post('*/api/dev/bulk', async ({ request }) => {
    const { count } = (await request.json()) as { count: number }
    return run(() => engine.addDefects(fakeDefects(count)))
  }),
  http.post('*/api/dev/reset', () => run(() => engine.reset())),

  /* 事件流:数据变化、提示和接受进度 */
  sse('*/api/events', ({ client }) => {
    const off = engine.subscribe((e) => {
      try {
        client.send({ data: JSON.stringify(e) })
      } catch {
        off()
      }
    })
  }),
]

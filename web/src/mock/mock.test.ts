import { setupServer } from 'msw/node'
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Defect } from '@/types/defect'
import type { ServerEvent } from '@/types/events'
import type { DefectList } from '@/types/list'
import { Engine, engine } from './engine'
import { handlers } from './handlers'

const make = () => new Engine({ random: () => 0.5 })
const state = (e: Engine, id: string) => e.getLists().find((l) => l.id === id)?.state
const d = (e: Engine, id: string) => e.getDefects().find((x) => x.id === id)!
const steps = (e: Engine, n: number) => Array.from({ length: n }, () => e.step())

describe('种子数据推导出的清单状态', () => {
  const e = make()
  it('紧急清单为空时是待处理(界面显示「空闲」)', () => expect(state(e, 'L-URGENT')).toBe('pending'))
  it('已开始且排在最前的清单处理中', () => expect(state(e, 'L-0001')).toBe('running'))
  it('被用户暂停、还有未处理完缺陷的清单是待处理', () => expect(state(e, 'L-0002')).toBe('pending'))
  it('没有未处理完缺陷的清单处理完成', () => expect(state(e, 'L-0003')).toBe('done'))
  it('从未开始的清单是待处理', () => expect(state(e, 'L-0004')).toBe('pending'))
  it('紧急清单置顶', () => expect(e.getLists()[0].id).toBe('L-URGENT'))
})

describe('AI 处理推进', () => {
  it('处理中的缺陷走完步骤后进入待审核,并自动开始下一个', () => {
    const e = make()
    expect(d(e, 'BUG-2476').state).toBe('analyzing')
    steps(e, 2)
    expect(d(e, 'BUG-2476').state).toBe('review')
    expect(d(e, 'BUG-2469').state).toBe('analyzing')
    expect(d(e, 'BUG-2469').step).toBe(0)
  })
  it('生成方案时,同清单里还有别的待审核缺陷,就标记待复核', () => {
    const e = make()
    steps(e, 2)
    expect(d(e, 'BUG-2476').needsRecheck).toBe(true)
  })
  it('建议类缺陷被 AI 自动跳过', () => {
    const e = make()
    e.addUrgent('SUG-1120', 'front')
    e.step()
    expect(d(e, 'SUG-1120').state).toBe('passed')
    expect(d(e, 'SUG-1120').outcome).toMatchObject({ kind: 'passed', auto: true })
  })
})

describe('紧急插队与恢复', () => {
  it('马上处理会打断当前缺陷,并保存为被插队暂停', () => {
    const e = make()
    e.addUrgent('BUG-2438', 'front')
    expect(d(e, 'BUG-2438').state).toBe('analyzing')
    expect(d(e, 'BUG-2476')).toMatchObject({ state: 'paused', pause: { cause: 'preempted' } })
    expect(state(e, 'L-URGENT')).toBe('running')
    expect(state(e, 'L-0001')).toBe('queued')
  })
  it('紧急缺陷处理完后自动恢复被打断的缺陷,从暂停的步骤继续', () => {
    const e = make()
    e.addUrgent('BUG-2438', 'front')
    steps(e, 3)
    expect(d(e, 'BUG-2438').state).toBe('review')
    expect(d(e, 'BUG-2476')).toMatchObject({ state: 'analyzing', step: 1 })
    expect(d(e, 'BUG-2476').rebased).toBeUndefined()
    expect(state(e, 'L-0001')).toBe('running')
  })
  it('紧急缺陷被接受、main 已更新后,恢复的缺陷要先同步最新 main', () => {
    vi.useFakeTimers()
    const e = make()
    e.addUrgent('BUG-2438', 'front')
    steps(e, 3)
    e.addUrgent('BUG-2420', 'front')
    e.accept('BUG-2438')
    vi.advanceTimersByTime(10_000)
    expect(e.mainRev).toBe(1)
    steps(e, 3)
    expect(d(e, 'BUG-2476').state).toBe('analyzing')
    expect(d(e, 'BUG-2476').rebased).toBe(true)
    vi.useRealTimers()
  })
  it('排在紧急队列后面不会打断当前的紧急缺陷', () => {
    const e = make()
    e.addUrgent('BUG-2438', 'front')
    e.addUrgent('BUG-2420', 'back')
    expect(d(e, 'BUG-2438').state).toBe('analyzing')
    expect(d(e, 'BUG-2420').state).toBe('queued')
  })
})

describe('清单队列', () => {
  it('暂停清单会保存进度,继续后排到队尾重新开始', () => {
    const e = make()
    e.pauseList('L-0001')
    expect(d(e, 'BUG-2476')).toMatchObject({ state: 'paused', pause: { cause: 'user' } })
    expect(state(e, 'L-0001')).toBe('pending')
    e.startList('L-0001')
    expect(state(e, 'L-0001')).toBe('running')
    expect(d(e, 'BUG-2476').state).toBe('analyzing')
  })
  it('继续处理一个清单时,前面有清单在处理就排队,不打断它', () => {
    const e = make()
    e.startList('L-0002')
    expect(state(e, 'L-0002')).toBe('queued')
    expect(state(e, 'L-0001')).toBe('running')
    expect(d(e, 'BUG-2476').state).toBe('analyzing')
  })
  it('优先处理会让清单插到队首,原来处理中的清单让位', () => {
    const e = make()
    e.startList('L-0002')
    e.jumpList('L-0002')
    expect(state(e, 'L-0002')).toBe('running')
    expect(state(e, 'L-0001')).toBe('queued')
    expect(d(e, 'BUG-2476')).toMatchObject({ state: 'paused', pause: { cause: 'preempted' } })
    expect(d(e, 'TST-0933').state).toBe('analyzing')
  })
  it('对待处理的清单点优先处理,等于开始并插队', () => {
    const e = make()
    e.jumpList('L-0004')
    expect(state(e, 'L-0004')).toBe('running')
    expect(state(e, 'L-0001')).toBe('queued')
  })
  it('处理完成的清单加入新的未处理缺陷后,自动重新处理', () => {
    const e = make()
    e.addToList('L-0003', 'BUG-2431')
    expect(state(e, 'L-0003')).toBe('queued')
  })
  it('创建、编辑和删除清单', () => {
    const e = make()
    const id = e.createList({ name: ' 新清单 ', defectIds: ['BUG-2431'] })
    expect(e.getLists().find((l) => l.id === id)).toMatchObject({ name: '新清单', state: 'pending' })
    e.updateList(id, { name: '改名', defectIds: ['BUG-2431', 'BUG-2420'] })
    expect(e.getLists().find((l) => l.id === id)?.defectIds).toHaveLength(2)
    e.deleteList(id)
    expect(e.getLists().some((l) => l.id === id)).toBe(false)
    expect(() => e.deleteList('L-URGENT')).toThrow()
  })
})

describe('审核流程', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('接受流程分 7 步汇报进度,完成后缺陷变为已接受', () => {
    const e = make()
    const events: ServerEvent[] = []
    e.subscribe((ev) => ev.type === 'accept-progress' && events.push(ev))
    e.accept('BUG-2481')
    vi.advanceTimersByTime(10_000)
    expect(d(e, 'BUG-2481').state).toBe('accepted')
    expect(d(e, 'BUG-2481').outcome).toMatchObject({ kind: 'accepted' })
    expect(events.map((ev) => ev.type === 'accept-progress' && ev.step)).toEqual([0, 1, 2, 3, 4, 5, 6, 7])
  })
  it('重复接受不会重复执行', () => {
    const e = make()
    e.accept('BUG-2481')
    e.accept('BUG-2481')
    vi.advanceTimersByTime(10_000)
    expect(e.mainRev).toBe(1)
  })
  it('复核会清除待复核标记并写入复核结果', () => {
    const e = make()
    e.recheck('BUG-2462')
    expect(d(e, 'BUG-2462').rechecking).toBe(true)
    vi.advanceTimersByTime(2000)
    expect(d(e, 'BUG-2462')).toMatchObject({ rechecking: false, needsRecheck: false })
    expect(d(e, 'BUG-2462').fix?.recheck).toBeTruthy()
  })
  it('拒绝可以选择是否保留修改', () => {
    const e = make()
    e.reject('BUG-2481', { keepChanges: true, reason: '  范围偏大 ' })
    expect(d(e, 'BUG-2481').outcome).toEqual({ kind: 'rejected', keepChanges: true, reason: '范围偏大' })
  })
  it('跳过会记录原因', () => {
    const e = make()
    e.pass('BUG-2481', '无法复现')
    expect(d(e, 'BUG-2481').outcome).toEqual({ kind: 'passed', auto: false, reason: '无法复现' })
  })
})

describe('通知与新缺陷', () => {
  it('收到新缺陷时默认不在任何清单里,并产生一条通知', () => {
    const e = make()
    const before = e.getNotifications().length
    const nd = e.simulateNewDefect()
    expect(e.getLists().some((l) => l.defectIds.includes(nd.id))).toBe(false)
    expect(e.getNotifications()).toHaveLength(before + 1)
  })
  it('安静的提示只弹出,不进入通知列表', () => {
    const e = make()
    const before = e.getNotifications().length
    e.pauseList('L-0001')
    expect(e.getNotifications()).toHaveLength(before)
  })
  it('标记已读', () => {
    const e = make()
    e.simulateNewDefect()
    e.markAllRead()
    expect(e.getNotifications().every((n) => !n.unread)).toBe(true)
  })
})

describe('假接口', () => {
  const server = setupServer(...handlers)
  beforeAll(() => server.listen({ onUnhandledRequest: 'error' }))
  beforeEach(() => engine.reset())
  afterAll(() => server.close())
  const post = (path: string, body?: unknown) =>
    fetch(`http://localhost/api${path}`, { method: 'POST', body: body ? JSON.stringify(body) : undefined })

  it('GET /api/defects 返回全部 13 条缺陷', async () => {
    const res = await fetch('http://localhost/api/defects')
    expect(((await res.json()) as Defect[]).length).toBe(13)
  })
  it('GET /api/defects/:id 找不到时返回 404', async () => {
    expect((await fetch('http://localhost/api/defects/NOPE')).status).toBe(404)
  })
  it('GET /api/lists 返回 5 个清单并带状态', async () => {
    const lists = (await (await fetch('http://localhost/api/lists')).json()) as DefectList[]
    expect(lists).toHaveLength(5)
    expect(lists.every((l) => l.state)).toBe(true)
  })
  it('POST 暂停清单后,清单变为待处理', async () => {
    expect((await post('/lists/L-0001/pause')).status).toBe(200)
    expect(engine.getLists().find((l) => l.id === 'L-0001')?.state).toBe('pending')
  })
  it('引擎报错时返回 400 和中文提示', async () => {
    const res = await fetch('http://localhost/api/lists/L-URGENT', { method: 'DELETE' })
    expect(res.status).toBe(400)
    expect(((await res.json()) as { message: string }).message).toBe('紧急清单不能删除')
  })
  it('批量生成缺陷', async () => {
    await post('/dev/bulk', { count: 300 })
    expect(engine.getDefects()).toHaveLength(313)
    expect(new Set(engine.getDefects().map((x) => x.id)).size).toBe(313)
  })
})

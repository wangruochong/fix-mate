import { describe, expect, it } from 'vitest'
import type { Defect } from '@/types/defect'
import type { DefectList } from '@/types/list'
import { firstReview, orderWithGhosts, pausedHighlight, pickViewList, rowExtra, urgentSummary } from './work'

const d = (id: string, state: Defect['state'], extra: Partial<Defect> = {}): Defect => ({
  id, title: id, type: 'Bug', priority: 'Major', requirement: 'r', version: 'v', reporter: 'x',
  createdAt: '2026-11-01T00:00:00Z', description: '', state, ...extra,
})
const l = (id: string, state: DefectList['state']): DefectList => ({ id, name: id, createdAt: '', defectIds: [], state })

describe('缺陷页辅助', () => {
  it('firstReview 取第一个待审核并可排除', () => {
    const ds = [d('a', 'accepted'), d('b', 'review'), d('c', 'review')]
    expect(firstReview(ds)?.id).toBe('b')
    expect(firstReview(ds, 'b')?.id).toBe('c')
  })
  it('被移出的缺陷插回原来的位置', () => {
    expect(orderWithGhosts(['a', 'c'], { b: 1 })).toEqual(['a', 'b', 'c'])
    expect(orderWithGhosts(['a'], { z: 9 })).toEqual(['a', 'z'])
    expect(orderWithGhosts(['a', 'b'], { b: 0 })).toEqual(['a', 'b'])
  })
  it('清单选择:选中的 > 处理中的 > 第一个', () => {
    const ls = [l('x', 'pending'), l('y', 'running'), l('z', 'done')]
    expect(pickViewList(ls, 'z')?.id).toBe('z')
    expect(pickViewList(ls, 'nope')?.id).toBe('y')
    expect(pickViewList([l('x', 'pending')], null)?.id).toBe('x')
    expect(pickViewList([], null)).toBeUndefined()
  })
  it('进度说明', () => {
    expect(rowExtra(d('a', 'analyzing', { step: 1 }))).toBe(' · 基于 main 建临时分支…')
    expect(rowExtra(d('a', 'paused', { step: 2, pause: { cause: 'user', at: '' } }))).toBe(' · 暂停于「修改代码并提交」')
    expect(rowExtra(d('a', 'paused', { pause: { cause: 'preempted', at: '' } }))).toBe(' · 紧急插队,已暂停')
    expect(rowExtra(d('a', 'queued'))).toBe('')
  })
  it('暂停高亮优先用户手动暂停的', () => {
    const ds = [d('a', 'paused', { pause: { cause: 'preempted', at: '' } }), d('b', 'paused', { pause: { cause: 'user', at: '' } })]
    expect(pausedHighlight(ds)?.id).toBe('b')
    expect(pausedHighlight([d('c', 'queued')])).toBeUndefined()
  })
  it('紧急提示条信息', () => {
    const s = urgentSummary([d('a', 'queued'), d('b', 'analyzing'), d('c', 'review')])
    expect(s.left.map((x) => x.id)).toEqual(['a', 'b'])
    expect(s.current.id).toBe('b')
    expect(s.ready?.id).toBe('c')
  })
})

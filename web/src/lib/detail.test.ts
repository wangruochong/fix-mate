import { describe, expect, it } from 'vitest'
import type { Defect } from '@/types/defect'
import type { DefectList, ListState } from '@/types/list'
import { nextReviewFor, partialResult, queuedInfo } from './detail'

const defect = (id: string, state: Defect['state']): Defect => ({
  id, title: id, type: 'Bug', priority: 'Major', requirement: 'r', version: 'v', reporter: 'x',
  createdAt: new Date().toISOString(), description: '', state,
})
const list = (id: string, state: ListState, defectIds: string[]): DefectList => ({
  id, name: `清单${id}`, createdAt: new Date().toISOString(), defectIds, state,
})
const mapOf = (...ds: Defect[]) => new Map(ds.map((d) => [d.id, d]))

describe('partialResult', () => {
  it('第 0 步还没有结论', () => {
    expect(partialResult({ id: 'BUG-1', step: 0 })).toEqual([['正在分析缺陷描述,还没有得出结论']])
  })
  it('第 1 步有判断和置信度', () => {
    expect(partialResult({ id: 'BUG-1', step: 1, pause: { cause: 'user', at: '', confidence: 92 } })).toEqual([
      ['判断完成:可通过修改代码解决,置信度 92%'],
    ])
  })
  it('第 2 步有分支、已有结果和工作目录说明', () => {
    const r = partialResult({ id: 'BUG-1', step: 2, pause: { cause: 'user', at: '', note: '完成了 3 个用例' } })
    expect(r).toHaveLength(4)
    expect(r[1]).toEqual(['已基于 main 创建临时分支 ', { code: 'fixmate/BUG-1' }])
    expect(r[2]).toEqual(['完成了 3 个用例'])
  })
})

describe('nextReviewFor', () => {
  const a = defect('A', 'accepted'), b = defect('B', 'review'), c = defect('C', 'review')
  const lists = [list('L1', 'running', ['A', 'B', 'C']), list('L2', 'pending', ['A']), list('L3', 'pending', ['B'])]
  it('取正在查看的清单里下一个待审核', () => {
    const r = nextReviewFor(a, lists, mapOf(a, b, c), 'L1')
    expect(r?.next.id).toBe('B')
    expect(r?.count).toBe(2)
  })
  it('正在查看的清单不含该缺陷时,取所属的第一个清单', () => {
    expect(nextReviewFor(a, lists, mapOf(a, b, c), 'L3')?.list.id).toBe('L1')
  })
  it('没有待审核的缺陷时返回空', () => {
    expect(nextReviewFor(a, [list('L2', 'pending', ['A'])], mapOf(a), null)).toBeUndefined()
  })
  it('不把自己算作下一个', () => {
    expect(nextReviewFor(b, lists, mapOf(a, b, c), 'L1')?.next.id).toBe('C')
  })
})

describe('queuedInfo', () => {
  const q1 = defect('Q1', 'analyzing'), q2 = defect('Q2', 'queued'), q3 = defect('Q3', 'queued'), r = defect('R', 'review')
  it('在活跃清单里:显示前面还有几个未处理完的缺陷', () => {
    const info = queuedInfo(q3, [list('L1', 'running', ['Q1', 'Q2', 'Q3'])], mapOf(q1, q2, q3))
    expect(info).toMatchObject({ kind: 'active', ahead: 2 })
  })
  it('清单没开始:提供开始处理', () => {
    const info = queuedInfo(q2, [list('L1', 'pending', ['Q2'])], mapOf(q2))
    expect(info).toMatchObject({ kind: 'listed', startLabel: '开始处理' })
  })
  it('清单被暂停过(有进度):提供继续处理', () => {
    const info = queuedInfo(q2, [list('L1', 'pending', ['R', 'Q2'])], mapOf(r, q2))
    expect(info).toMatchObject({ kind: 'listed', startLabel: '继续处理' })
  })
  it('清单在排队:说明前面的清单处理完后会自动开始', () => {
    const info = queuedInfo(q2, [list('L1', 'queued', ['Q2'])], mapOf(q2))
    expect(info).toMatchObject({ kind: 'listed' })
    expect((info as { text: string }).text).toContain('正在排队')
  })
  it('不在任何清单里', () => {
    expect(queuedInfo(q2, [], mapOf(q2))).toEqual({ kind: 'unlisted' })
  })
})

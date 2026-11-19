import { describe, expect, it } from 'vitest'
import type { Defect } from '@/types/defect'
import {
  distinctValues,
  emptyFilter,
  filterCount,
  filterDefects,
  hiddenSelectedCount,
  listedIds,
  selectAllVisible,
  toggleItem,
} from './list-editor'

const mk = (id: string, o: Partial<Defect> = {}): Defect => ({
  id,
  title: id,
  type: 'Bug',
  priority: 'Major',
  requirement: '账号体系改版',
  version: 'v3.8.0',
  reporter: '',
  createdAt: '',
  description: '',
  state: 'queued',
  ...o,
})

const defects = [
  mk('A', { type: 'Bug', priority: 'Blocker' }),
  mk('B', { type: '建议', priority: 'Minor', version: 'v3.7.2' }),
  mk('C', { type: 'Bug', priority: 'Minor', requirement: '报表中心' }),
]
const lists = [{ defectIds: ['A'] }]

describe('清单编辑器的筛选', () => {
  it('没有条件时不过滤', () => {
    expect(filterDefects(defects, emptyFilter(), lists)).toHaveLength(3)
    expect(filterCount(emptyFilter())).toBe(0)
  })
  it('类型和优先级内部是「或」,之间是「且」', () => {
    const f = { ...emptyFilter(), types: new Set(['Bug' as const, '建议' as const]), priorities: new Set(['Minor' as const]) }
    expect(filterDefects(defects, f, lists).map((d) => d.id)).toEqual(['B', 'C'])
    expect(filterCount(f)).toBe(3)
  })
  it('按版本和需求精确匹配', () => {
    expect(filterDefects(defects, { ...emptyFilter(), version: 'v3.7.2' }, lists).map((d) => d.id)).toEqual(['B'])
    expect(filterDefects(defects, { ...emptyFilter(), requirement: '报表中心' }, lists).map((d) => d.id)).toEqual(['C'])
  })
  it('只看未入清单的缺陷', () => {
    expect(filterDefects(defects, { ...emptyFilter(), unlistedOnly: true }, lists).map((d) => d.id)).toEqual(['B', 'C'])
  })
  it('候选值去重并保持顺序', () => {
    expect(distinctValues(defects, 'version')).toEqual(['v3.8.0', 'v3.7.2'])
  })
  it('列出所有已入清单的缺陷', () => {
    expect([...listedIds([{ defectIds: ['A', 'B'] }, { defectIds: ['B', 'C'] }])].sort()).toEqual(['A', 'B', 'C'])
  })
})

describe('已选集合运算', () => {
  it('切换不修改原集合', () => {
    const s = new Set(['A'])
    expect([...toggleItem(s, 'B')]).toEqual(['A', 'B'])
    expect([...toggleItem(s, 'A')]).toEqual([])
    expect([...s]).toEqual(['A'])
  })
  it('全选只加入当前可见的,保留已选的隐藏项', () => {
    const next = selectAllVisible(new Set(['Z']), [{ id: 'A' }, { id: 'B' }])
    expect([...next].sort()).toEqual(['A', 'B', 'Z'])
  })
  it('统计被筛选隐藏的已选数量', () => {
    expect(hiddenSelectedCount(new Set(['A', 'Z', 'Y']), [{ id: 'A' }])).toBe(2)
  })
})

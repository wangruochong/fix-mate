import type { Defect, DefectType, Priority } from '@/types/defect'
import type { DefectList } from '@/types/list'

/** 清单编辑器里的缺陷筛选条件。version / requirement 为空字符串表示不筛选。 */
export interface EditorFilter {
  types: ReadonlySet<DefectType>
  priorities: ReadonlySet<Priority>
  version: string
  requirement: string
  /** 只看还没加入任何清单的缺陷 */
  unlistedOnly: boolean
}

export const emptyFilter = (): EditorFilter => ({
  types: new Set(),
  priorities: new Set(),
  version: '',
  requirement: '',
  unlistedOnly: false,
})

/** 生效的筛选条件个数,类型和优先级每选一项算一个。 */
export const filterCount = (f: EditorFilter) =>
  f.types.size + f.priorities.size + (f.version ? 1 : 0) + (f.requirement ? 1 : 0) + (f.unlistedOnly ? 1 : 0)

/** 所有出现在任何清单里的缺陷 id。 */
export const listedIds = (lists: Pick<DefectList, 'defectIds'>[]) => new Set(lists.flatMap((l) => l.defectIds))

export function matchesFilter(d: Defect, f: EditorFilter, listed: ReadonlySet<string>) {
  if (f.types.size && !f.types.has(d.type)) return false
  if (f.priorities.size && !f.priorities.has(d.priority)) return false
  if (f.version && d.version !== f.version) return false
  if (f.requirement && d.requirement !== f.requirement) return false
  if (f.unlistedOnly && listed.has(d.id)) return false
  return true
}

export const filterDefects = (defects: Defect[], f: EditorFilter, lists: Pick<DefectList, 'defectIds'>[]) => {
  const listed = listedIds(lists)
  return defects.filter((d) => matchesFilter(d, f, listed))
}

/** 版本、需求的候选值:全部缺陷里不重复的值,保持首次出现的顺序。 */
export const distinctValues = (defects: Defect[], key: 'version' | 'requirement') => [...new Set(defects.map((d) => d[key]))]

export function toggleItem<T>(set: ReadonlySet<T>, item: T): Set<T> {
  const next = new Set(set)
  if (!next.delete(item)) next.add(item)
  return next
}

/** 把当前可见的缺陷全部加入已选。 */
export const selectAllVisible = (selected: ReadonlySet<string>, visible: Pick<Defect, 'id'>[]) =>
  new Set([...selected, ...visible.map((d) => d.id)])

/** 已选中、但被筛选条件隐藏的缺陷个数。 */
export const hiddenSelectedCount = (selected: ReadonlySet<string>, visible: Pick<Defect, 'id'>[]) => {
  const shown = new Set(visible.map((d) => d.id))
  let n = 0
  for (const id of selected) if (!shown.has(id)) n++
  return n
}

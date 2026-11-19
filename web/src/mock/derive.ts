import { isUndone, type Defect } from '@/types/defect'
import type { DefectList, ListState } from '@/types/list'
import type { ListRecord } from './seed'

const hasUndone = (l: ListRecord, byId: Map<string, Defect>) =>
  l.defectIds.some((id) => {
    const d = byId.get(id)
    return d !== undefined && isUndone(d)
  })

/** 当前被 AI 处理的清单:紧急清单优先,否则取排在最前的已开始清单。 */
export function activeList(lists: ListRecord[], byId: Map<string, Defect>) {
  const candidates = lists.filter((l) => l.on && hasUndone(l, byId))
  return candidates.find((l) => l.urgent) ?? [...candidates].sort((a, b) => a.seq - b.seq)[0]
}

/** 清单状态完全由缺陷状态和清单的开始标记推导,见设计文档第 4 节。 */
export function listState(l: ListRecord, lists: ListRecord[], byId: Map<string, Defect>): ListState {
  if (!hasUndone(l, byId)) return l.defectIds.length === 0 ? 'pending' : 'done'
  if (!l.on) return 'pending'
  return activeList(lists, byId) === l ? 'running' : 'queued'
}

/** 紧急清单置顶,其余保持创建顺序。 */
export function toApiLists(lists: ListRecord[], defects: Defect[]): DefectList[] {
  const byId = new Map(defects.map((d) => [d.id, d]))
  return [...lists]
    .sort((a, b) => Number(!!b.urgent) - Number(!!a.urgent))
    .map((l) => ({
      id: l.id,
      name: l.name,
      urgent: l.urgent,
      createdAt: l.createdAt,
      defectIds: [...l.defectIds],
      state: listState(l, lists, byId),
    }))
}

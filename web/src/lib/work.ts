import { STEPS } from '@/lib/defect'
import { isUndone, type Defect } from '@/types/defect'
import type { DefectList } from '@/types/list'

/** 清单里第一个待审核的缺陷,可排除某个缺陷。 */
export function firstReview(defects: Defect[], excludeId?: string) {
  return defects.find((d) => d.state === 'review' && d.id !== excludeId)
}

/**
 * 缺陷页要显示的缺陷顺序:清单自己的顺序,再把刚被移出但侧栏还没关的缺陷(ghost)插回原位。
 */
export function orderWithGhosts(defectIds: string[], ghosts: Record<string, number>) {
  const order = [...defectIds]
  Object.entries(ghosts)
    .sort((a, b) => a[1] - b[1])
    .forEach(([id, index]) => {
      if (!order.includes(id)) order.splice(Math.min(index, order.length), 0, id)
    })
  return order
}

/** 缺陷页当前要显示的清单:用户选的,否则正在处理的,否则第一个。 */
export function pickViewList(lists: DefectList[], viewListId: string | null) {
  return lists.find((l) => l.id === viewListId) ?? lists.find((l) => l.state === 'running') ?? lists[0]
}

/** 缺陷行第二行末尾的进度说明。 */
export function rowExtra(d: Defect) {
  if (d.state === 'analyzing') return ` · ${STEPS[Math.min(d.step ?? 0, 2)]}…`
  if (d.state === 'paused') return d.pause?.cause === 'preempted' ? ' · 紧急插队,已暂停' : ` · 暂停于「${STEPS[d.step ?? 0]}」`
  return ''
}

/** 清单已暂停时,横幅里要提到的缺陷:优先用户手动暂停的。 */
export function pausedHighlight(defects: Defect[]) {
  return defects.find((d) => d.state === 'paused' && d.pause?.cause === 'user') ?? defects.find((d) => d.state === 'paused')
}

/** 紧急提示条需要的信息:还没处理完的紧急缺陷、正在处理的那个、已就绪等审核的那个。 */
export function urgentSummary(urgentDefects: Defect[]) {
  const left = urgentDefects.filter(isUndone)
  return {
    left,
    current: left.find((d) => d.state === 'analyzing') ?? left[0],
    ready: urgentDefects.find((d) => d.state === 'review'),
  }
}

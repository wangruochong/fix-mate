import type { Defect, DefectState, DefectType, Priority } from '@/types/defect'
import type { DefectList } from '@/types/list'

export const STATE_LABEL: Record<DefectState, string> = {
  review: '待审核',
  paused: '已暂停',
  analyzing: 'AI 处理中',
  queued: '排队中',
  passed: '已跳过',
  accepted: '已接受',
  rejected: '已拒绝',
}

/** AI 处理的四个步骤,最后一步是等待用户审核。 */
export const STEPS = ['判断是否可修复', '基于 main 建临时分支', '修改代码并提交', '等待你审核'] as const

export const FINAL_STATES: readonly DefectState[] = ['accepted', 'rejected', 'passed']

export const isFinal = (d: Pick<Defect, 'state'>) => FINAL_STATES.includes(d.state)

export const PRIORITY_COLOR: Record<Priority, string> = {
  Blocker: '#D4443C',
  Critical: '#E0701F',
  Major: '#C99A0B',
  Minor: '#7B879C',
}

export const PRIORITIES = Object.keys(PRIORITY_COLOR) as Priority[]

export const DEFECT_TYPES: DefectType[] = ['Bug', '建议', '测试需求', '历史遗留问题']

export const listsOf = (lists: DefectList[], defectId: string) => lists.filter((l) => l.defectIds.includes(defectId))

/** 清单有没有处理进度,直接从缺陷状态算出来,不单独存标记。 */
export const listHasProgress = (defects: Pick<Defect, 'state'>[]) => defects.some((d) => d.state !== 'queued')

/** 排队中的缺陷,只要所在清单已被用户开始(处理中或排队中),界面就显示「排队中」,否则显示「未开始」。 */
export const isQueuedLive = (lists: DefectList[], defectId: string) =>
  listsOf(lists, defectId).some((l) => l.state === 'running' || l.state === 'queued')

/** 缺陷是否在紧急清单里。 */
export const isInUrgent = (lists: DefectList[], defectId: string) =>
  lists.some((l) => l.urgent && l.defectIds.includes(defectId))

export const canUrgent = (lists: DefectList[], d: Defect) =>
  (d.state === 'queued' || d.state === 'paused' || d.state === 'analyzing') && !isInUrgent(lists, d.id)

/** 模糊匹配:查询字符按顺序出现在目标里即可。 */
export function fuzzy(query: string, target: string) {
  const q = query.toLowerCase().replace(/\s/g, '')
  const s = target.toLowerCase().replace(/\s/g, '')
  let i = 0
  for (const c of s) if (c === q[i]) i++
  return i === q.length
}

/** 先匹配包含关键词的,再追加模糊匹配的。 */
export function searchDefects(defects: Defect[], query: string) {
  const q = query.trim()
  if (!q) return []
  const exact = defects.filter((d) => d.title.toLowerCase().includes(q.toLowerCase()))
  const loose = defects.filter((d) => !exact.includes(d) && fuzzy(q, d.title))
  return [...exact, ...loose]
}

import { isUndone, type Defect, type RichText } from '@/types/defect'
import type { DefectList } from '@/types/list'
import { listHasProgress, listsOf } from './defect'

/** 已暂停缺陷的「已保存的中间结果」,由暂停时所处的步骤、已有结果和分支名生成。 */
export function partialResult(d: Pick<Defect, 'id' | 'step' | 'pause'>): RichText[] {
  const step = d.step ?? 0
  const lines: RichText[] = []
  lines.push(
    step >= 1
      ? [`判断完成:可通过修改代码解决,置信度 ${d.pause?.confidence ?? 90}%`]
      : ['正在分析缺陷描述,还没有得出结论'],
  )
  if (step >= 2) {
    lines.push(['已基于 main 创建临时分支 ', { code: `fixmate/${d.id}` }])
    lines.push([d.pause?.note ?? '已定位到相关代码,已完成的修改保存在临时分支上'])
    lines.push(['暂停时未提交的修改保存在该缺陷独立的工作目录里,不影响你自己的工作区'])
  }
  return lines
}

/**
 * 缺陷进入终态后,同一清单里下一个待审核的缺陷。
 * 优先用正在查看的清单(且缺陷在其中),否则取缺陷所属的第一个清单。
 */
export function nextReviewFor(
  d: Pick<Defect, 'id'>,
  lists: DefectList[],
  defectMap: Map<string, Defect>,
  viewListId: string | null,
) {
  const viewing = viewListId ? lists.find((l) => l.id === viewListId) : undefined
  const list = viewing?.defectIds.includes(d.id) ? viewing : listsOf(lists, d.id)[0]
  if (!list) return undefined
  const reviews = list.defectIds
    .map((id) => defectMap.get(id))
    .filter((x): x is Defect => !!x && x.state === 'review' && x.id !== d.id)
  return reviews.length ? { list, next: reviews[0], count: reviews.length } : undefined
}

export type QueuedInfo =
  | { kind: 'active'; list: DefectList; ahead: number }
  | { kind: 'listed'; list: DefectList; text: string; startLabel?: '开始处理' | '继续处理' }
  | { kind: 'unlisted' }

/** 排队中的缺陷:它在哪个清单、前面还有几个、该显示什么说明和操作。 */
export function queuedInfo(d: Pick<Defect, 'id'>, lists: DefectList[], defectMap: Map<string, Defect>): QueuedInfo {
  const active = lists.find((l) => l.state === 'running')
  if (active?.defectIds.includes(d.id)) {
    const ahead = active.defectIds
      .slice(0, active.defectIds.indexOf(d.id))
      .map((id) => defectMap.get(id))
      .filter((x) => x && isUndone(x)).length
    return { kind: 'active', list: active, ahead }
  }
  const mine = listsOf(lists, d.id)
  if (!mine.length) return { kind: 'unlisted' }
  const progress = (l: DefectList) =>
    listHasProgress(l.defectIds.map((id) => defectMap.get(id)).filter((x): x is Defect => !!x))
  const rank = (l: DefectList) =>
    l.state === 'running' ? 0 : l.state === 'queued' ? 1 : l.state === 'pending' ? (progress(l) ? 2 : 3) : 4
  const list = [...mine].sort((a, b) => rank(a) - rank(b))[0]
  if (list.state === 'queued') {
    return { kind: 'listed', list, text: `所在清单「${list.name}」正在排队,前面的清单处理完后会自动开始。` }
  }
  if (list.state === 'pending') {
    const resumed = progress(list)
    return {
      kind: 'listed',
      list,
      text: resumed ? `所在清单「${list.name}」已暂停。` : `所在清单「${list.name}」还没开始处理。`,
      startLabel: resumed ? '继续处理' : '开始处理',
    }
  }
  return { kind: 'listed', list, text: `所在清单「${list.name}」还没开始处理。` }
}

import { Check, Clock, Pause, SkipForward, X } from 'lucide-react'
import { cn } from 'cn'
import { isInUrgent, isQueuedLive, PRIORITY_COLOR, STATE_LABEL } from '@/lib/defect'
import { isUndone, type Defect, type DefectState, type Priority } from '@/types/defect'
import type { DefectList, ListState } from '@/types/list'
import { Spinner } from './feedback'
import { Tag } from './tag'

export function PriorityDot({ priority }: { priority: Priority }) {
  return (
    <span className="inline-flex items-center gap-[5px] text-xs text-muted-foreground">
      <i className="size-[7px] rounded-full" style={{ background: PRIORITY_COLOR[priority] }} />
      {priority}
    </span>
  )
}

/** 缺陷行最左边的状态图标。 */
export function StateIcon({ state }: { state: DefectState }) {
  const base = 'grid size-[22px] shrink-0 place-items-center rounded-full'
  switch (state) {
    case 'analyzing':
      return (
        <div className={base}>
          <Spinner />
        </div>
      )
    case 'review':
      return (
        <div className={cn(base, 'border-2 border-primary bg-primary-soft')}>
          <span className="size-1.5 rounded-full bg-primary" />
        </div>
      )
    case 'queued':
      return (
        <div className={cn(base, 'text-faint')}>
          <Clock className="size-[15px]" />
        </div>
      )
    case 'paused':
      return (
        <div className={cn(base, 'bg-warning-soft text-warning')}>
          <Pause className="size-[11px]" />
        </div>
      )
    case 'passed':
      return (
        <div className={cn(base, 'text-faint')}>
          <SkipForward className="size-3" />
        </div>
      )
    case 'accepted':
      return (
        <div className={cn(base, 'bg-success-soft text-success')}>
          <Check className="size-3" />
        </div>
      )
    case 'rejected':
      return (
        <div className={cn(base, 'bg-danger-soft text-danger')}>
          <X className="size-3" />
        </div>
      )
  }
}

const STATE_TONE = {
  review: 'soft',
  analyzing: 'soft',
  queued: 'gray',
  paused: 'warn',
  passed: 'gray',
  accepted: 'good',
  rejected: 'bad',
} as const

/** 缺陷状态标签。排队中但所在清单还没开始时,显示「未开始」(仍是同一个状态)。 */
export function StateBadge({ defect, lists }: { defect: Pick<Defect, 'id' | 'state'>; lists: DefectList[] }) {
  const label = defect.state === 'queued' && !isQueuedLive(lists, defect.id) ? '未开始' : STATE_LABEL[defect.state]
  return <Tag tone={STATE_TONE[defect.state]}>{label}</Tag>
}

const LIST_LABEL: Record<ListState, string> = { pending: '待处理', queued: '排队中', running: '处理中', done: '处理完成' }

/** 清单状态标签。紧急清单为空时显示「空闲」;待处理且有进度时用琥珀色提示是暂停过的。 */
export function ListBadge({ list, hasProgress }: { list: DefectList; hasProgress?: boolean }) {
  const idle = list.urgent && list.defectIds.length === 0
  const tone = list.state === 'running' ? 'soft' : list.state === 'done' ? 'good' : list.state === 'pending' && hasProgress ? 'warn' : 'gray'
  return (
    <Tag tone={tone}>
      {list.state === 'running' && <i className="size-1.5 animate-pulse-dot rounded-full bg-current" />}
      {idle ? '空闲' : LIST_LABEL[list.state]}
    </Tag>
  )
}

/** 缺陷所属清单的标签,最多显示 max 个,不在任何清单里显示「未入清单」。 */
export function ListChips({ lists, defectId, max = 2 }: { lists: DefectList[]; defectId: string; max?: number }) {
  const mine = lists.filter((l) => l.defectIds.includes(defectId))
  if (!mine.length) return <Tag tone="warn">未入清单</Tag>
  return (
    <>
      {mine.slice(0, max).map((l) => (
        <Tag key={l.id} tone="list" title={l.name}>
          {l.name}
        </Tag>
      ))}
      {mine.length > max && <Tag>+{mine.length - max}</Tag>}
    </>
  )
}

/** 紧急标签:在紧急清单里且还没处理完的缺陷才显示。 */
export function UrgentTag({ defect, lists }: { defect: Pick<Defect, 'id' | 'state'>; lists: DefectList[] }) {
  if (!isInUrgent(lists, defect.id) || !isUndone(defect)) return null
  return <Tag tone="urgent">紧急</Tag>
}

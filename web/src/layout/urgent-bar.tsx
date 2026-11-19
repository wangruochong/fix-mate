import { ChevronRight, Flame } from 'lucide-react'
import { cn } from 'cn'
import { useAppData } from '@/api/queries'
import { Tag } from '@/components/common/tag'
import { urgentSummary } from '@/lib/work'
import { useUi } from '@/store/ui'
import type { Defect } from '@/types/defect'

/** 任何页面顶部的紧急提示条,点击打开对应缺陷。 */
export function UrgentBar() {
  const { lists, defectMap } = useAppData()
  const openDetail = useUi((s) => s.openDetail)
  const urgent = lists.find((l) => l.urgent)
  if (!urgent) return null
  const { left, current, ready } = urgentSummary(urgent.defectIds.map((id) => defectMap.get(id)).filter((d): d is Defect => !!d))
  const yielded = lists.some((l) => !l.urgent && l.state === 'queued')

  const bar = (ok: boolean, target: Defect, content: React.ReactNode, action: string) => (
    <button
      type="button"
      onClick={() => openDetail(target.id)}
      className={cn(
        'flex flex-none items-center gap-2.5 border-b px-[22px] py-[9px] text-left text-[13px]',
        ok ? 'border-success/30 bg-success-soft [&_svg]:text-success [&_b]:text-success' : 'border-urgent/30 bg-urgent-soft [&_svg]:text-urgent [&_b]:text-urgent',
      )}
    >
      <Flame className="size-4" />
      {content}
      <span className="inline-flex items-center gap-0.5 text-[12.5px] whitespace-nowrap text-muted-foreground">
        {action}
        <ChevronRight className="size-3.5" />
      </span>
    </button>
  )

  if (left.length && urgent.state === 'running' && current) {
    return bar(
      false,
      current,
      <>
        <b>紧急处理中</b>
        <span className="min-w-0 flex-1 truncate">
          {current.id} · {current.title}
        </span>
        {left.length > 1 && <Tag tone="urgent">还有 {left.length - 1} 个排队</Tag>}
        {yielded && <span className="text-xs whitespace-nowrap text-muted-foreground">其它清单已暂时让位,处理完会自动恢复</span>}
      </>,
      '查看',
    )
  }
  if (ready) {
    return bar(
      true,
      ready,
      <>
        <b>紧急缺陷已就绪</b>
        <span className="min-w-0 flex-1 truncate">
          {ready.id} · {ready.title}
        </span>
      </>,
      '去审核',
    )
  }
  return null
}

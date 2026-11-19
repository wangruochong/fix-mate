import { AlertTriangle, Bell, Check, PartyPopper, SkipForward, type LucideIcon } from 'lucide-react'
import { toast } from 'sonner'
import { useUi } from '@/store/ui'
import type { NotificationKind } from '@/types/events'

export const NOTIFICATION_STYLE: Record<NotificationKind, { icon: LucideIcon; box: string }> = {
  new: { icon: Bell, box: 'bg-primary-soft text-primary' },
  ok: { icon: Check, box: 'bg-success-soft text-success' },
  skip: { icon: SkipForward, box: 'bg-subtle text-muted-foreground' },
  done: { icon: PartyPopper, box: 'bg-success-soft text-success' },
  warn: { icon: AlertTriangle, box: 'bg-warning-soft text-warning' },
}

interface ToastInput {
  title: string
  body: string
  kind: NotificationKind
  defectId?: string
  /** 安静的提示显示时间更短 */
  quiet?: boolean
}

/** 右上角提示。点击后如果关联了缺陷,会打开它的详情。 */
export function showToast({ title, body, kind, defectId, quiet }: ToastInput) {
  const { icon: Icon, box } = NOTIFICATION_STYLE[kind]
  toast.custom(
    (id) => (
      <div
        role="status"
        onClick={() => {
          toast.dismiss(id)
          if (defectId) useUi.getState().openDetail(defectId)
        }}
        className="flex w-[340px] cursor-pointer gap-[11px] rounded-lg border bg-popover p-3 shadow-pop"
      >
        <div className={`grid size-8 shrink-0 place-items-center rounded-md ${box}`}>
          <Icon className="size-[17px]" />
        </div>
        <div className="min-w-0">
          <b className="block text-[13.5px]">{title}</b>
          <span className="block text-[12.5px] text-muted-foreground">{body}</span>
        </div>
      </div>
    ),
    { duration: quiet ? 3200 : 6500 },
  )
}

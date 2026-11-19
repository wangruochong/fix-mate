import { Bell, Bug, Layers, Search, Settings, type LucideIcon } from 'lucide-react'
import { cn } from 'cn'
import { actions } from '@/api/actions'
import { useAppData, useNotifications } from '@/api/queries'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { NOTIFICATION_STYLE } from '@/lib/toast'
import { timeAgo } from '@/lib/format'
import { useUi, type View } from '@/store/ui'

function Tab({ label, icon: Icon, active, dot, ...props }: { label: string; icon: LucideIcon; active?: boolean; dot?: boolean } & React.ComponentProps<'button'>) {
  return (
    <button
      type="button"
      className={cn(
        'relative flex size-[58px] flex-col items-center justify-center gap-1 rounded-xl text-xs font-medium text-muted-foreground transition-colors hover:bg-subtle hover:text-foreground',
        active && 'bg-primary-soft text-primary-text hover:bg-primary-soft hover:text-primary-text',
        active && 'before:absolute before:top-[17px] before:bottom-[17px] before:-left-[9px] before:w-[3px] before:rounded-r-[3px] before:bg-primary',
      )}
      {...props}
    >
      <Icon className="size-[22px]" />
      <span>{label}</span>
      {dot && <i className="absolute top-[9px] right-3 size-[9px] rounded-full border-2 border-card bg-danger" />}
    </button>
  )
}

function Notifications() {
  const { data: notifications = [] } = useNotifications()
  const unread = notifications.some((n) => n.unread)
  const openDetail = useUi((s) => s.openDetail)
  return (
    <Popover onOpenChange={(open) => open && unread && void actions.markNotificationsRead()}>
      <PopoverTrigger render={<Tab label="通知" icon={Bell} dot={unread} />} />
      <PopoverContent side="right" align="start" sideOffset={12} className="w-[360px] gap-0 overflow-hidden rounded-lg p-0 shadow-pop">
        <h4 className="flex justify-between border-b px-4 py-3 text-[13.5px]">
          <b>通知</b>
          <span className="text-faint">{notifications.length} 条</span>
        </h4>
        {notifications.length === 0 && <div className="p-6 text-center text-faint">暂无通知</div>}
        <div className="max-h-[420px] overflow-auto">
          {notifications.slice(0, 8).map((n) => {
            const { icon: Icon, box } = NOTIFICATION_STYLE[n.kind]
            return (
              <button
                type="button"
                key={n.id}
                onClick={() => n.defectId && openDetail(n.defectId)}
                className="flex w-full gap-2.5 border-b px-4 py-[11px] text-left text-[13px] last:border-0 hover:bg-panel-2"
              >
                <i className={cn('mt-[7px] size-[7px] shrink-0 rounded-full', n.unread ? 'bg-primary' : 'bg-transparent')} />
                <div className={cn('grid size-7 shrink-0 place-items-center rounded-md', box)}>
                  <Icon className="size-[15px]" />
                </div>
                <div className="min-w-0">
                  <b className="block">{n.title}</b>
                  <span className="block text-muted-foreground">{n.body}</span>
                  <small className="block text-faint">{timeAgo(n.createdAt)}</small>
                </div>
              </button>
            )
          })}
        </div>
      </PopoverContent>
    </Popover>
  )
}

/** 左侧竖栏:缺陷、清单、搜索三个页签,下方一条横线,线下是通知和设置。 */
export function Rail() {
  const view = useUi((s) => s.view)
  const go = useUi((s) => s.go)
  const { defects, lists } = useAppData()
  const hasUnlisted = defects.some((d) => !lists.some((l) => l.defectIds.includes(d.id)))
  const tab = (v: View, label: string, icon: LucideIcon, dot?: boolean) => (
    <Tab label={label} icon={icon} active={view === v} dot={dot} onClick={() => go(v)} />
  )
  return (
    <nav className="z-2 flex w-(--rail-w) flex-none flex-col items-center gap-1.5 border-r bg-card pt-4 pb-[18px]">
      <div className="mb-[18px] grid size-[38px] place-items-center rounded-xl bg-gradient-to-br from-[#7a7af0] to-[#4b4bc8] text-[19px] font-extrabold text-white shadow-[0_6px_16px_rgb(91_91_214/0.35)]">
        F
      </div>
      {tab('work', '缺陷', Bug)}
      {tab('lists', '清单', Layers, hasUnlisted)}
      {tab('search', '搜索', Search)}
      <div className="my-2 h-px w-[34px] bg-border" />
      <Notifications />
      {tab('settings', '设置', Settings)}
      <div className="flex-1" />
      <div className="grid size-8 place-items-center rounded-full bg-primary-soft text-[13px] font-semibold text-primary-text">我</div>
    </nav>
  )
}

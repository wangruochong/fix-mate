import { cn } from 'cn'
import { useUi } from '@/store/ui'

/**
 * 页面内容容器。详情侧栏打开时,内容区缩到侧栏左边,不再居中,
 * 这样侧栏旁边的列表仍然完整可见。
 */
export function PageContainer({ className, children }: { className?: string; children: React.ReactNode }) {
  const detailOpen = useUi((s) => s.drawer?.kind === 'detail')
  return (
    <div
      className={cn(
        'mx-auto max-w-[980px] px-8 pb-[110px]',
        detailOpen && 'm-0 w-[calc(100vw-var(--rail-w)-var(--drawer-w))] max-w-none px-6',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function PageHeader({ title, desc, children }: { title: React.ReactNode; desc?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="pt-[30px] pb-[18px]">
      <div className="flex items-start gap-4">
        <div>
          <h1 className="mb-0.5 text-2xl font-bold tracking-[0.2px]">{title}</h1>
          {desc && <div className="text-muted-foreground">{desc}</div>}
        </div>
        <div className="flex-1" />
        {children}
      </div>
    </div>
  )
}

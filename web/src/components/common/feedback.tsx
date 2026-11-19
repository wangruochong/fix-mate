import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from 'cn'
import type { LucideIcon } from 'lucide-react'

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      className={cn('inline-block size-4 animate-spin-slow rounded-full border-2 border-primary-soft border-t-primary', className)}
    />
  )
}

/** 横幅提示条:warn 琥珀(默认)、info 主色、ok 绿色。 */
const bannerVariants = cva('mb-[18px] flex items-center gap-3 rounded-lg border px-4 py-3', {
  variants: {
    tone: {
      warn: 'border-warning/25 bg-warning-soft [&>svg]:text-warning',
      info: 'border-primary/25 bg-primary-soft [&>svg]:text-primary',
      ok: 'border-success/25 bg-success-soft [&>svg]:text-success',
    },
  },
  defaultVariants: { tone: 'warn' },
})

export function Banner({
  tone,
  icon: Icon,
  title,
  desc,
  children,
}: VariantProps<typeof bannerVariants> & { icon: LucideIcon; title: React.ReactNode; desc?: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className={bannerVariants({ tone })}>
      <Icon className="size-[18px]" />
      <div className="min-w-0 flex-1">
        <b className="block">{title}</b>
        {desc && <span className="text-[12.5px] text-muted-foreground">{desc}</span>}
      </div>
      {children}
    </div>
  )
}

/** 空状态:大图标、标题、说明、可选按钮。 */
export function EmptyBlock({
  icon: Icon,
  title,
  desc,
  children,
}: {
  icon: LucideIcon
  title: string
  desc: React.ReactNode
  children?: React.ReactNode
}) {
  return (
    <div className="mx-auto max-w-[380px] py-16 text-center text-muted-foreground">
      <div className="mx-auto mb-4 grid size-16 place-items-center rounded-[20px] bg-primary-soft text-primary">
        <Icon className="size-[30px]" />
      </div>
      <h2 className="mb-1.5 text-[17px] font-semibold text-foreground">{title}</h2>
      <p>{desc}</p>
      {children && <div className="mt-[18px]">{children}</div>}
    </div>
  )
}

/** 信息卡片。warn 琥珀底、info 主色底。 */
const cardVariants = cva('rounded-xl border bg-card px-[18px] py-4', {
  variants: {
    tone: {
      default: '',
      warn: 'border-warning/30 bg-warning-soft',
      info: 'border-primary/25 bg-primary-soft',
    },
  },
  defaultVariants: { tone: 'default' },
})

export function Card({ tone, className, ...props }: React.ComponentProps<'div'> & VariantProps<typeof cardVariants>) {
  return <div className={cn(cardVariants({ tone }), className)} {...props} />
}

export function CardTitle({
  icon: Icon,
  children,
  sub,
}: {
  icon?: LucideIcon | React.ComponentType<{ className?: string }>
  children: React.ReactNode
  sub?: React.ReactNode
}) {
  return (
    <div className="mb-2 flex items-center gap-2 font-semibold">
      {Icon && <Icon className="size-4" />}
      {children}
      {sub && <span className="ml-auto text-xs font-normal text-faint">{sub}</span>}
    </div>
  )
}

/** 卡片内的小注释块。 */
export function Note({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('mt-3.5 rounded-lg border bg-panel-2 px-3 py-2.5 text-[12.5px] text-muted-foreground', className)} {...props} />
}

export function Mono({ className, ...props }: React.ComponentProps<'span'>) {
  return <span className={cn('font-mono text-xs', className)} {...props} />
}

export function Hint({ className, ...props }: React.ComponentProps<'div'>) {
  return <div className={cn('flex items-start gap-1.5 text-xs leading-snug text-muted-foreground', className)} {...props} />
}

/** 进度条。value 为 0 到 100。 */
export function ProgressBar({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cn('h-1.5 overflow-hidden rounded-[3px] bg-subtle', className)}>
      <i className="block h-full rounded-[3px] bg-gradient-to-r from-[#7a7af0] to-primary transition-[width] duration-500" style={{ width: `${value}%` }} />
    </div>
  )
}

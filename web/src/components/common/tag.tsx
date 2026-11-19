import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from 'cn'

/** 小标签。tone 对应设计稿里的几种底色。 */
const tagVariants = cva('inline-flex h-5 items-center gap-1 rounded-sm px-2 text-[11.5px] font-semibold whitespace-nowrap', {
  variants: {
    tone: {
      accent: 'bg-primary text-primary-foreground',
      soft: 'bg-primary-soft text-primary-text',
      warn: 'bg-warning-soft text-warning',
      good: 'bg-success-soft text-success',
      bad: 'bg-danger-soft text-danger',
      gray: 'bg-subtle text-muted-foreground',
      urgent: 'bg-urgent-soft text-urgent',
      /** 清单名,白底描边,过长截断 */
      list: 'inline-block max-w-[120px] truncate border bg-card font-normal leading-[18px] text-muted-foreground',
    },
  },
  defaultVariants: { tone: 'gray' },
})

export function Tag({ tone, className, ...props }: React.ComponentProps<'span'> & VariantProps<typeof tagVariants>) {
  return <span className={cn(tagVariants({ tone }), className)} {...props} />
}

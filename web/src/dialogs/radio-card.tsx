import { cn } from 'cn'

/** 单选卡片:圆形单选点 + 标题 + 说明。 */
export function RadioCard({
  selected,
  onSelect,
  title,
  children,
}: {
  selected: boolean
  onSelect: () => void
  title: string
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'mb-2.5 flex w-full gap-3 rounded-lg border-[1.5px] px-3.5 py-3 text-left transition-colors',
        selected ? 'border-primary bg-primary-soft' : 'hover:border-faint',
      )}
    >
      <span
        className={cn(
          'mt-0.5 grid size-[18px] shrink-0 place-items-center rounded-full border-2',
          selected ? 'border-primary' : 'border-faint',
        )}
      >
        {selected && <span className="size-2 rounded-full bg-primary" />}
      </span>
      <span className="min-w-0">
        <b className="block font-semibold">{title}</b>
        <span className="text-[12.5px] text-muted-foreground">{children}</span>
      </span>
    </button>
  )
}

import { cn } from 'cn'
import { useState } from 'react'

/** 开关。传 checked 为受控,否则内部记住状态。label 给读屏器用。 */
export function Switch({
  checked,
  defaultChecked = false,
  onCheckedChange,
  label,
}: {
  checked?: boolean
  defaultChecked?: boolean
  onCheckedChange?: (checked: boolean) => void
  label: string
}) {
  const [inner, setInner] = useState(defaultChecked)
  const on = checked ?? inner
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      onClick={() => {
        setInner(!on)
        onCheckedChange?.(!on)
      }}
      className={cn(
        'relative h-[22px] w-[38px] shrink-0 rounded-full bg-border transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/30',
        'after:absolute after:top-0.5 after:left-0.5 after:size-[18px] after:rounded-full after:bg-white after:shadow-[0_1px_3px_rgb(0_0_0/0.25)] after:transition-[left]',
        on && 'bg-primary after:left-[18px]',
      )}
    />
  )
}

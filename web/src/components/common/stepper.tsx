import { Check, Pause } from 'lucide-react'
import { cn } from 'cn'
import { STEPS } from '@/lib/defect'
import { Card } from './feedback'

/** AI 处理的四个步骤。cur 是当前步骤,paused 表示停在这一步。 */
export function Stepper({ cur, paused }: { cur: number; paused?: boolean }) {
  return (
    <Card>
      <div className="flex">
        {STEPS.map((label, i) => {
          const done = i < cur
          const current = i === cur
          return (
            <div
              key={label}
              className={cn(
                'relative flex flex-1 flex-col gap-1.5 text-[12.5px] text-faint',
                'after:absolute after:top-2.5 after:right-0 after:left-[22px] after:h-0.5 after:bg-subtle last:after:hidden',
                done && 'text-muted-foreground after:bg-success',
                current && !paused && 'font-semibold text-foreground',
                current && paused && 'font-semibold text-warning',
              )}
            >
              <div
                className={cn(
                  'relative z-10 grid size-[22px] place-items-center rounded-full bg-subtle text-[11px] font-bold text-faint',
                  done && 'bg-success text-white',
                  current && !paused && 'bg-primary text-primary-foreground',
                  current && paused && 'bg-warning text-white',
                )}
              >
                {done ? <Check className="size-3" /> : current && paused ? <Pause className="size-[11px]" /> : i + 1}
              </div>
              {label}
            </div>
          )
        })}
      </div>
    </Card>
  )
}

import { Flame } from 'lucide-react'
import { actions } from '@/api/actions'
import { useAppData } from '@/api/queries'
import { Button } from '@/components/ui/button'
import { canUrgent } from '@/lib/defect'
import { useUi } from '@/store/ui'
import type { Defect } from '@/types/defect'
import { isUndone } from '@/types/defect'

/**
 * 「立即处理」按钮。紧急队列空闲时直接开始;已有紧急缺陷在处理时,弹出选择位置的对话框。
 * 只有未处理完、且不在紧急清单里的缺陷才会显示。
 */
export function UrgentButton({ defect, size = 'sm' }: { defect: Defect; size?: 'sm' | 'default' }) {
  const { lists, defectMap } = useAppData()
  if (!canUrgent(lists, defect)) return null
  const onClick = (e: React.MouseEvent) => {
    e.stopPropagation()
    const urgent = lists.find((l) => l.urgent)
    const busy = urgent?.defectIds.map((id) => defectMap.get(id)).filter((d): d is Defect => !!d && isUndone(d)) ?? []
    if (busy.length === 0) void actions.setUrgent(defect.id, 'front')
    else useUi.getState().openDialog({ kind: 'urgent', defectId: defect.id })
  }
  return (
    <Button variant="urgent" size={size} onClick={onClick}>
      <Flame />
      立即处理
    </Button>
  )
}

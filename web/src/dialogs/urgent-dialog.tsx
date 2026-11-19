import { Flame } from 'lucide-react'
import { useState } from 'react'
import { actions } from '@/api/actions'
import { useAppData } from '@/api/queries'
import { Note } from '@/components/common/feedback'
import { Button } from '@/components/ui/button'
import { useUi } from '@/store/ui'
import { isUndone, type Defect } from '@/types/defect'
import { DialogShell } from './dialog-shell'
import { RadioCard } from './radio-card'

/** 紧急队列里已经有缺陷时,选择新缺陷的位置:马上处理(打断当前)或排在后面。 */
export function UrgentDialog() {
  const dialog = useUi((s) => s.dialog)
  const closeDialog = useUi((s) => s.closeDialog)
  return dialog?.kind === 'urgent' ? <UrgentBody defectId={dialog.defectId} onClose={closeDialog} /> : null
}

function UrgentBody({ defectId, onClose }: { defectId: string; onClose: () => void }) {
  const { lists, defectMap } = useAppData()
  const [position, setPosition] = useState<'front' | 'back'>('front')
  const urgent = lists.find((l) => l.urgent)
  const busy = (urgent?.defectIds ?? []).map((id) => defectMap.get(id)).filter((d): d is Defect => !!d && isUndone(d))
  const current = busy.find((d) => d.state === 'analyzing') ?? busy[0]

  const confirm = async () => {
    try {
      await actions.setUrgent(defectId, position)
      onClose()
    } catch {
      /* 错误提示已由 actions 弹出 */
    }
  }

  return (
    <DialogShell
      open
      onClose={onClose}
      title={`立即处理 ${defectId}`}
      desc={`紧急队列里已经有 ${busy.length} 个缺陷,请选择这个缺陷的位置。`}
      footer={
        <>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button onClick={() => void confirm()}>
            <Flame />
            确认
          </Button>
        </>
      }
    >
      <RadioCard selected={position === 'front'} onSelect={() => setPosition('front')} title="马上处理">
        打断正在处理的 {current?.id},保存它的进度,先处理这个缺陷
      </RadioCard>
      <RadioCard selected={position === 'back'} onSelect={() => setPosition('back')} title="排在紧急队列后面">
        不打断当前的紧急缺陷,依次处理
      </RadioCard>
      <Note className="mt-1">被打断的缺陷会保存进度,等更紧急的处理完后按顺序自动恢复。</Note>
    </DialogShell>
  )
}

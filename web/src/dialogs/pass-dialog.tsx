import { useState } from 'react'
import { actions } from '@/api/actions'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useUi } from '@/store/ui'
import { DialogShell } from './dialog-shell'

const PRESET_REASONS = ['需求不明确', '无法复现', '不是代码问题', '稍后处理']

/** 跳过:不改任何代码,必须写原因。 */
export function PassDialog() {
  const dialog = useUi((s) => s.dialog)
  const closeDialog = useUi((s) => s.closeDialog)
  return dialog?.kind === 'pass' ? <PassBody defectId={dialog.defectId} onClose={closeDialog} /> : null
}

function PassBody({ defectId, onClose }: { defectId: string; onClose: () => void }) {
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const valid = reason.trim().length > 0

  const submit = async () => {
    setBusy(true)
    try {
      await actions.pass(defectId, reason.trim())
      onClose()
    } catch {
      setBusy(false)
    }
  }

  return (
    <DialogShell
      open
      onClose={onClose}
      title={`跳过 ${defectId}`}
      desc="跳过后不会修改任何代码,请简单备注原因。"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button disabled={!valid || busy} onClick={() => void submit()}>确认跳过</Button>
        </>
      }
    >
      <div className="mb-2.5 flex flex-wrap gap-[7px]">
        {PRESET_REASONS.map((r) => (
          <button
            key={r}
            type="button"
            onClick={() => setReason(r)}
            className="inline-flex h-7 items-center rounded-full border bg-card px-[11px] text-[12.5px] text-muted-foreground transition-colors hover:border-faint"
          >
            {r}
          </button>
        ))}
      </div>
      <Textarea
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="跳过原因(必填)"
        className="h-[84px] resize-none text-[14px]"
      />
    </DialogShell>
  )
}

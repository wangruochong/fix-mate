import { useState } from 'react'
import { actions } from '@/api/actions'
import { Mono } from '@/components/common/feedback'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import { useUi } from '@/store/ui'
import { DialogShell } from './dialog-shell'
import { RadioCard } from './radio-card'

/** 拒绝方案:可选保留 AI 的修改,可选填原因。 */
export function RejectDialog() {
  const dialog = useUi((s) => s.dialog)
  const closeDialog = useUi((s) => s.closeDialog)
  const open = dialog?.kind === 'reject'
  return open ? <RejectBody defectId={dialog.defectId} onClose={closeDialog} /> : null
}

function RejectBody({ defectId, onClose }: { defectId: string; onClose: () => void }) {
  const [keep, setKeep] = useState(true)
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async () => {
    setBusy(true)
    try {
      await actions.reject(defectId, { keepChanges: keep, reason: reason.trim() || undefined })
      onClose()
    } catch {
      setBusy(false)
    }
  }

  return (
    <DialogShell
      open
      onClose={onClose}
      title={`拒绝 ${defectId} 的修复方案`}
      desc="被拒绝的方案仍可能有价值,你可以选择是否保留。"
      footer={
        <>
          <Button variant="outline" onClick={onClose}>取消</Button>
          <Button variant="danger" disabled={busy} onClick={() => void submit()}>确认拒绝</Button>
        </>
      }
    >
      <RadioCard selected={keep} onSelect={() => setKeep(true)} title="保留 AI 的修改">
        用 <Mono>git cherry-pick -n</Mono> 放入 main 工作区(不提交),方便你在此基础上继续改
      </RadioCard>
      <RadioCard selected={!keep} onSelect={() => setKeep(false)} title="丢弃修改">
        仅删除临时分支,不改动 main
      </RadioCard>
      <label className="mt-1.5 mb-1.5 block text-[12.5px] text-muted-foreground" htmlFor="reject-reason">
        拒绝原因(可选)
      </label>
      <Textarea
        id="reject-reason"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="例如:思路对,但改动范围偏大"
        className="h-[84px] resize-none text-[14px]"
      />
    </DialogShell>
  )
}

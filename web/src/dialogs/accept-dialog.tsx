import { Check, X } from 'lucide-react'
import { cn } from 'cn'
import { actions } from '@/api/actions'
import { useAppData } from '@/api/queries'
import { Note, Spinner } from '@/components/common/feedback'
import { Rich } from '@/components/common/rich'
import { Button } from '@/components/ui/button'
import { useUi } from '@/store/ui'
import { ACCEPT_STEP_NAMES, acceptStepText, acceptSteps } from '@/lib/accept'
import type { Defect } from '@/types/defect'
import { DialogShell } from './dialog-shell'

/** 接受方案:先确认,确认后展示 7 步进度,可转到后台继续。 */
export function AcceptDialog() {
  const dialog = useUi((s) => s.dialog)
  const closeDialog = useUi((s) => s.closeDialog)
  const { defectMap } = useAppData()
  const defect = dialog?.kind === 'accept' ? defectMap.get(dialog.defectId) : undefined
  return defect?.fix ? <AcceptBody defect={defect} onClose={closeDialog} /> : null
}

function AcceptBody({ defect, onClose }: { defect: Defect; onClose: () => void }) {
  const progress = useUi((s) => s.acceptProgress[defect.id])
  const branch = defect.fix!.branch
  const step = progress?.step ?? -1
  const finished = step >= 7
  const failed = progress?.error !== undefined

  const confirm = async () => {
    useUi.getState().setAcceptProgress(defect.id, { step: 0 })
    try {
      await actions.accept(defect.id)
    } catch {
      useUi.getState().clearAcceptProgress(defect.id)
    }
  }
  const done = () => {
    useUi.getState().clearAcceptProgress(defect.id)
    onClose()
  }

  if (!progress) {
    return (
      <DialogShell
        open
        onClose={onClose}
        title={`接受 ${defect.id} 的修复方案`}
        desc="确认后将自动完成以下步骤,无需手动操作。"
        footer={
          <>
            <Button variant="outline" onClick={onClose}>取消</Button>
            <Button variant="good" onClick={() => void confirm()}>
              <Check />
              确认接受
            </Button>
          </>
        }
      >
        <ul className="flex flex-col gap-0.5">
          {acceptSteps(branch).map((text, i) => (
            <StepRow key={i} index={i} state="todo">
              <Rich text={text} />
            </StepRow>
          ))}
        </ul>
        <Note>
          评论格式:<code className="font-mono text-xs">#{'{ota_version}'}</code>,例如 <code className="font-mono text-xs">#3.8.0.2417</code>
        </Note>
      </DialogShell>
    )
  }

  // 失败:关闭时清掉进度,下次打开又是确认页;也可以直接点重试,会从失败的那一步继续
  if (failed) {
    return (
      <DialogShell
        open
        onClose={done}
        title={`接受 ${defect.id} 卡在了第 ${step + 1} 步`}
        desc={progress.error}
        footer={
          <>
            <Button variant="outline" onClick={done}>关闭</Button>
            <Button onClick={() => void confirm()}>重试接受</Button>
          </>
        }
      >
        <ul className="flex flex-col gap-0.5">
          {acceptSteps(branch).map((_, i) => (
            <StepRow key={i} index={i} state={i < step ? 'ok' : i === step ? 'fail' : 'todo'}>
              <Rich text={i === step ? [`${ACCEPT_STEP_NAMES[i]}(失败)`] : acceptStepText(branch, i, step, progress.ota)} />
            </StepRow>
          ))}
        </ul>
        <Note>已完成的步骤不会重做。如果失败的是「打 OTA 包」或「飞书评论」,请先确认它是否已经生效,再重试。</Note>
      </DialogShell>
    )
  }

  return (
    <DialogShell
      open
      onClose={finished ? done : onClose}
      title={finished ? '已接受并发布' : `正在处理 ${defect.id}`}
      desc={finished ? '缺陷已标记为已接受。' : '请稍候,期间可以关闭窗口,过程在后台继续。'}
      footer={
        finished ? (
          <Button onClick={done}>完成</Button>
        ) : (
          <Button variant="outline" onClick={onClose}>转到后台</Button>
        )
      }
    >
      <ul className="flex flex-col gap-0.5">
        {acceptSteps(branch).map((_, i) => (
          <StepRow key={i} index={i} state={i < step ? 'ok' : i === step ? 'run' : 'todo'}>
            <Rich text={acceptStepText(branch, i, step, progress.ota)} />
          </StepRow>
        ))}
      </ul>
    </DialogShell>
  )
}

function StepRow({ index, state, children }: { index: number; state: 'todo' | 'run' | 'ok' | 'fail'; children: React.ReactNode }) {
  return (
    <li className={cn('flex items-center gap-2.5 px-1 py-[7px] text-[13.5px] text-muted-foreground', state !== 'todo' && 'text-foreground', state === 'fail' && 'text-danger')}>
      <span
        className={cn(
          'grid size-5 shrink-0 place-items-center rounded-full bg-subtle text-[11px] font-bold text-faint',
          state === 'run' && 'bg-transparent',
          state === 'ok' && 'bg-success text-white',
          state === 'fail' && 'bg-danger text-white',
        )}
      >
        {state === 'ok' ? <Check className="size-3" /> : state === 'fail' ? <X className="size-3" /> : state === 'run' ? <Spinner /> : index + 1}
      </span>
      <span>{children}</span>
    </li>
  )
}

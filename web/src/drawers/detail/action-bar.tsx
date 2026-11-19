import { Check, ChevronRight, Pause, Play, SkipForward, X } from 'lucide-react'
import { actions } from '@/api/actions'
import { Button } from '@/components/ui/button'
import { isFinal, listsOf, STEPS } from '@/lib/defect'
import { nextReviewFor, queuedInfo } from '@/lib/detail'
import { useUi } from '@/store/ui'
import type { Defect } from '@/types/defect'
import type { DefectList } from '@/types/list'

function Bar({ hint, children }: { hint: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div className="flex-none border-t bg-card px-6 py-3.5">
      <div className="flex items-center gap-2.5">
        <span className="flex-1 text-xs leading-snug text-muted-foreground">{hint}</span>
        {children}
      </div>
    </div>
  )
}

function reviewHint(defect: Defect) {
  if (defect.needsRecheck) return '请先完成复核,再接受该方案'
  if (defect.acceptError) return '上次接受没有完成,重试会从失败的那一步继续,已完成的步骤不会重做'
  return '接受后将 cherry-pick 到 main、push 并通过 Jenkins 打 OTA'
}

/** 底部固定操作栏,随缺陷状态变化。没有可做的操作时返回空。 */
export function ActionBar({ defect, lists, defectMap }: { defect: Defect; lists: DefectList[]; defectMap: Map<string, Defect> }) {
  const openDialog = useUi((s) => s.openDialog)
  const openDetail = useUi((s) => s.openDetail)
  const viewListId = useUi((s) => s.viewListId)
  const accepting = useUi((s) => {
    const p = s.acceptProgress[defect.id]
    return !!p && p.step < 7 && !p.error
  })
  const id = defect.id

  // 终态之后,如果同一清单里还有待审核的缺陷,引导去下一个
  if (isFinal(defect)) {
    const r = nextReviewFor(defect, lists, defectMap, viewListId)
    if (!r) return null
    return (
      <Bar hint={`「${r.list.name}」还有 ${r.count} 个待审核的缺陷`}>
        <Button onClick={() => openDetail(r.next.id)}>
          下一个待审核
          <ChevronRight />
        </Button>
      </Bar>
    )
  }

  switch (defect.state) {
    case 'review': {
      const blocked = !!defect.needsRecheck || !!defect.rechecking || accepting
      return (
        <Bar hint={reviewHint(defect)}>
          <Button variant="outline" onClick={() => openDialog({ kind: 'pass', defectId: id })}>
            <SkipForward />
            跳过
          </Button>
          <Button variant="danger" onClick={() => openDialog({ kind: 'reject', defectId: id })}>
            <X />
            拒绝
          </Button>
          <Button variant="good" size="lg" disabled={blocked} onClick={() => openDialog({ kind: 'accept', defectId: id })}>
            <Check />
            {defect.acceptError ? '重试接受' : '接受并发布'}
          </Button>
        </Bar>
      )
    }

    case 'analyzing':
      return (
        <Bar hint="暂停后会保存当前进度,之后可以从这里接着处理">
          <Button variant="outline" onClick={() => void actions.pauseDefect(id)}>
            <Pause />
            暂停修复
          </Button>
        </Bar>
      )

    case 'paused': {
      const mine = listsOf(lists, id)
      const live = mine.some((l) => l.state === 'running' || l.state === 'queued')
      if (defect.pause?.cause === 'preempted' && live) return <Bar hint="紧急处理完成后会自动恢复,无需手动操作" />
      return (
        <Bar
          hint={
            mine.length
              ? `继续后从「${STEPS[defect.step ?? 0]}」接着处理,不会重复已完成的步骤`
              : '它不在任何清单中,先加入清单才能继续'
          }
        >
          <Button disabled={!mine.length} onClick={() => void actions.resumeDefect(id)}>
            <Play />
            继续修复
          </Button>
        </Bar>
      )
    }

    case 'queued': {
      const info = queuedInfo(defect, lists, defectMap)
      if (info.kind !== 'listed' || !info.startLabel) return null
      return (
        <Bar hint="开始后,AI 会按清单顺序逐个修复">
          <Button onClick={() => void actions.startList(info.list.id)}>
            <Play />
            {info.startLabel}「{info.list.name}」
          </Button>
        </Bar>
      )
    }
  }
  return null
}

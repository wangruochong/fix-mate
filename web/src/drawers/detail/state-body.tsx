import { Check, Clock, Flame, Pause, RefreshCw, SkipForward, X } from 'lucide-react'
import { actions } from '@/api/actions'
import { Card, CardTitle, Mono, Note, Spinner } from '@/components/common/feedback'
import { Rich } from '@/components/common/rich'
import { Stepper } from '@/components/common/stepper'
import { Tag } from '@/components/common/tag'
import { Button } from '@/components/ui/button'
import { isQueuedLive, STEPS } from '@/lib/defect'
import { partialResult, queuedInfo } from '@/lib/detail'
import { clock } from '@/lib/format'
import type { Defect } from '@/types/defect'
import type { DefectList } from '@/types/list'
import { FixCards } from './fix-cards'

const SKELETON = 'my-2 h-3 animate-shimmer rounded-sm bg-[linear-gradient(90deg,var(--subtle),var(--panel-2),var(--subtle))] bg-[length:200%_100%]'

/** 详情主体里随状态变化的部分。描述、所属清单等公共部分在 detail-drawer 里。 */
export function StateBody({ defect, lists, defectMap }: { defect: Defect; lists: DefectList[]; defectMap: Map<string, Defect> }) {
  const step = defect.step ?? 0
  switch (defect.state) {
    case 'review':
      return (
        <>
          {defect.needsRecheck && <RecheckCard defect={defect} />}
          {defect.fix && <FixCards fix={defect.fix} />}
        </>
      )

    case 'analyzing':
      return (
        <>
          <Stepper cur={Math.min(step, 2)} />
          {defect.rebased && (
            <Card tone="info">
              <CardTitle icon={RefreshCw}>已同步最新代码</CardTitle>
              <p className="opacity-90">
                紧急修复已合入 main。AI 已把这个缺陷的临时分支变基到最新 main,并结合之前保存的中间结果快速复核,然后从暂停处继续。
              </p>
            </Card>
          )}
          <Card>
            <CardTitle icon={Spinner} sub={`${STEPS[Math.min(step, 2)]}…`}>
              AI 正在处理
            </CardTitle>
            <div className={SKELETON} style={{ width: '90%' }} />
            <div className={SKELETON} style={{ width: '72%' }} />
            <div className={SKELETON} style={{ width: '81%' }} />
          </Card>
        </>
      )

    case 'paused':
      return (
        <>
          <Stepper cur={step} paused />
          {defect.pause?.cause === 'preempted' && (
            <Card tone="info">
              <CardTitle icon={Flame}>被紧急缺陷打断</CardTitle>
              <p className="opacity-90">AI 去处理更紧急的缺陷了,已保存这个缺陷的进度。紧急缺陷处理完后会自动恢复,不需要手动操作。</p>
            </Card>
          )}
          <Card tone="warn">
            <CardTitle icon={Pause} sub={`暂停于 ${defect.pause ? clock(defect.pause.at) : '--'}`}>
              已保存的中间结果
            </CardTitle>
            <ul className="flex list-disc flex-col gap-1 pl-[18px]">
              {partialResult(defect).map((line, i) => (
                <li key={i}>
                  <Rich text={line} />
                </li>
              ))}
            </ul>
          </Card>
        </>
      )

    case 'queued':
      return <QueuedCard defect={defect} lists={lists} defectMap={defectMap} />

    case 'passed':
      return (
        <Card>
          <CardTitle icon={SkipForward}>
            已跳过
            {defect.outcome?.kind === 'passed' && defect.outcome.auto && <Tag tone="soft">AI 自动判断</Tag>}
          </CardTitle>
          <p className="opacity-90">{defect.outcome?.kind === 'passed' ? defect.outcome.reason : ''}</p>
        </Card>
      )

    case 'rejected': {
      const o = defect.outcome?.kind === 'rejected' ? defect.outcome : undefined
      return (
        <Card>
          <CardTitle icon={X}>已拒绝该方案</CardTitle>
          <p className="opacity-90">{o?.reason || '未填写原因'}</p>
          <div className="mt-3.5 flex flex-wrap gap-2.5">
            <Tag tone={o?.keepChanges ? 'good' : 'gray'}>{o?.keepChanges ? '已保留 AI 修改' : '已丢弃 AI 修改'}</Tag>
          </div>
          {o?.keepChanges && (
            <Note>
              修改已通过 <Mono>git cherry-pick -n</Mono> 放入 main 的工作区(未提交),临时分支已删除。
            </Note>
          )}
        </Card>
      )
    }

    case 'accepted': {
      const o = defect.outcome?.kind === 'accepted' ? defect.outcome : undefined
      return (
        <Card>
          <CardTitle icon={Check} sub={o ? `commit ${o.commit}` : undefined}>
            已接受并发布
          </CardTitle>
          <ul className="flex flex-col gap-2">
            {['已 cherry-pick 到 main 并 push', '已删除本地临时分支', 'Jenkins 已打包 OTA', '飞书缺陷已标记为已解决'].map((t) => (
              <li key={t} className="flex items-center gap-2 text-[13px] text-muted-foreground">
                <Check className="size-3.5 text-success" />
                {t}
              </li>
            ))}
          </ul>
          {o && (
            <>
              <div className="mt-3.5 flex flex-wrap gap-2.5">
                <Tag tone="good">OTA {o.ota}</Tag>
              </div>
              <div className="mt-2.5 rounded-lg border bg-panel-2 px-3 py-2.5 text-[13px]">
                <span className="text-faint">已在飞书评论:</span> <Mono>#{o.ota}</Mono>
              </div>
            </>
          )}
        </Card>
      )
    }
  }
}

/** 待复核:说明原因、给出缓存结论,并提供「立即复核」。 */
function RecheckCard({ defect }: { defect: Defect }) {
  return (
    <Card tone="info">
      <CardTitle
        icon={RefreshCw}
        sub={defect.cached ? `生成于 ${clock(defect.cached.at)} · 基线 ${defect.cached.baseCommit}` : undefined}
      >
        此方案需要复核
      </CardTitle>
      <p className="opacity-90">
        该方案生成于你审核其它缺陷期间,基于较早的代码。接受前,AI 会结合<b>最新 main</b> 与下方<b>缓存结论</b>重新评估,避免与已合入的修改冲突。
      </p>
      {defect.cached && (
        <div className="mt-3 rounded-lg border border-dashed bg-panel-2 px-3 py-2.5 text-[13px] text-muted-foreground">
          <b className="text-foreground">缓存结论</b>:{defect.cached.text}
        </div>
      )}
      <div className="mt-3">
        <Button size="sm" disabled={defect.rechecking} onClick={() => void actions.recheck(defect.id)}>
          {defect.rechecking ? (
            <>
              <Spinner />
              正在复核…
            </>
          ) : (
            <>
              <RefreshCw />
              立即复核
            </>
          )}
        </Button>
      </div>
    </Card>
  )
}

/** 排队中:区分在活跃清单里、所在清单未开始或在排队、不在任何清单里几种情况。 */
function QueuedCard({ defect, lists, defectMap }: { defect: Defect; lists: DefectList[]; defectMap: Map<string, Defect> }) {
  const info = queuedInfo(defect, lists, defectMap)
  if (info.kind === 'active') {
    return (
      <Card>
        <CardTitle icon={Clock}>排队中</CardTitle>
        <p className="opacity-90">「{info.list.name}」正在按顺序处理,前面还有 {info.ahead} 个缺陷,轮到它时会自动开始。</p>
      </Card>
    )
  }
  if (info.kind === 'unlisted') {
    return (
      <Card>
        <CardTitle icon={Clock}>未开始</CardTitle>
        <p className="opacity-90">它还不在任何清单中。加入清单并开始处理后,AI 才会修复它。</p>
      </Card>
    )
  }
  return (
    <Card>
      <CardTitle icon={Clock}>{isQueuedLive(lists, defect.id) ? '排队中' : '未开始'}</CardTitle>
      <p className="opacity-90">{info.text}</p>
    </Card>
  )
}

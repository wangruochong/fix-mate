import { AlertTriangle, ChevronRight, File, GitBranch, Layers, RefreshCw, Sparkles } from 'lucide-react'
import { useState } from 'react'
import { cn } from 'cn'
import { Card, CardTitle, Mono } from '@/components/common/feedback'
import { Rich } from '@/components/common/rich'
import { Stepper } from '@/components/common/stepper'
import { Tag } from '@/components/common/tag'
import type { Fix, FixFile } from '@/types/defect'

const chip = 'inline-flex h-7 items-center gap-1.5 rounded-md bg-subtle px-2.5 text-[12.5px] text-muted-foreground'

/** 待审核缺陷的 AI 判断、修复方案(含可折叠的代码对比)、复核结果和关联提示。 */
export function FixCards({ fix }: { fix: Fix }) {
  const additions = fix.files.reduce((a, f) => a + f.additions, 0)
  const deletions = fix.files.reduce((a, f) => a + f.deletions, 0)
  return (
    <>
      <Card>
        <CardTitle icon={Sparkles}>
          AI 判断
          <Tag tone="good">可通过代码修复 · 置信度 {fix.confidence}%</Tag>
        </CardTitle>
        <p className="opacity-90">{fix.judge}</p>
      </Card>

      <Stepper cur={3} />

      <Card>
        <CardTitle icon={Layers} sub={`${fix.files.length} 个文件 · +${additions} −${deletions}`}>
          修复方案
        </CardTitle>
        <ul className="flex list-disc flex-col gap-1 pl-[18px]">
          {fix.summary.map((s, i) => (
            <li key={i}>
              <Rich text={s} />
            </li>
          ))}
        </ul>
        <div className="mt-3 flex flex-wrap gap-2">
          <span className={chip}>
            <GitBranch className="size-[13px]" />
            <Mono>{fix.branch}</Mono>
          </span>
          <span className={cn(chip, 'font-mono text-xs')}>{fix.commit}</span>
          <span className={chip}>基于 main</span>
        </div>
        <div className="mt-3 rounded-lg border border-dashed bg-panel-2 px-3 py-2.5 text-[13px] text-muted-foreground">
          <b className="text-foreground">结论摘要</b>(已缓存,供后续缺陷参考):
          <Rich text={fix.conclusion} />
        </div>
        {fix.files.map((f, i) => (
          <FileDiff key={f.name} file={f} defaultOpen={i === 0} />
        ))}
      </Card>

      {fix.recheck && (
        <Card tone="info">
          <CardTitle icon={RefreshCw}>复核结果</CardTitle>
          <p className="opacity-90">{fix.recheck}</p>
        </Card>
      )}

      {fix.conflicts.length > 0 && (
        <Card tone="warn">
          <CardTitle icon={AlertTriangle}>关联提示</CardTitle>
          {fix.conflicts.map((c) => (
            <p key={`${c.with}-${c.file}`} className="opacity-90">
              与 <b>{c.with}</b> 修改了同一文件 <Mono>{c.file}</Mono>(第 {c.range} 行附近)。建议先处理 {c.with},再复核本方案。
            </p>
          ))}
        </Card>
      )}
    </>
  )
}

const LINE_STYLE = {
  add: 'bg-success-soft text-success',
  del: 'bg-danger-soft text-danger',
  ctx: 'text-faint',
  hunk: 'text-faint',
} as const

/** 一个文件的改动,点击标题折叠或展开。 */
function FileDiff({ file, defaultOpen }: { file: FixFile; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="mt-2.5 overflow-hidden rounded-md border">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 bg-panel-2 px-3 py-2 text-left text-[12.5px]"
        aria-expanded={open}
      >
        <ChevronRight className={cn('size-3.5 text-faint transition-transform', open && 'rotate-90')} />
        <File className="size-3.5" />
        <Mono>{file.name}</Mono>
        <span className="flex-1" />
        <Mono className="text-success">+{file.additions}</Mono>
        <Mono className="text-danger">−{file.deletions}</Mono>
      </button>
      {open && (
        <div className="overflow-auto font-mono text-xs leading-[1.65]">
          {file.lines.map((l, i) => (
            <div key={i} className={cn('px-3 whitespace-pre', LINE_STYLE[l.kind])}>
              {l.text}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

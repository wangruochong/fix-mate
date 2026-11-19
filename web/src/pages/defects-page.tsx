import { Check, ChevronDown, Clock, Flame, FolderOpen, GitBranch, Info, Layers, Pause, Play } from 'lucide-react'
import { useEffect, useState } from 'react'
import { cn } from 'cn'
import { actions } from '@/api/actions'
import { useAppData } from '@/api/queries'
import { Banner, EmptyBlock, ProgressBar } from '@/components/common/feedback'
import { ListBadge, PriorityDot, StateBadge, StateIcon, UrgentTag } from '@/components/common/defect-bits'
import { Tag } from '@/components/common/tag'
import { ListActionButton } from '@/components/list-action'
import { PageContainer } from '@/components/page'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { isUndone, type Defect } from '@/types/defect'
import type { DefectList } from '@/types/list'
import { listHasProgress, listsOf, STEPS } from '@/lib/defect'
import { shortDate } from '@/lib/format'
import { firstReview, orderWithGhosts, pausedHighlight, pickViewList, rowExtra } from '@/lib/work'
import { useUi } from '@/store/ui'

const listMeta = (l: DefectList) => (l.urgent ? `${l.defectIds.length} 个缺陷 · 插队处理` : `${l.defectIds.length} 个缺陷 · 创建于 ${shortDate(l.createdAt)}`)

function DefectRow({ defect: d, index, current, ghost, leaving }: { defect: Defect; index: number; current: boolean; ghost: boolean; leaving: boolean }) {
  const { lists } = useAppData()
  const selected = useUi((s) => s.drawer?.kind === 'detail' && s.drawer.defectId === d.id)
  const openDetail = useUi((s) => s.openDetail)
  const stop = (fn: () => void) => (e: React.MouseEvent) => {
    e.stopPropagation()
    fn()
  }
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => openDetail(d.id)}
      onKeyDown={(e) => e.key === 'Enter' && openDetail(d.id)}
      className={cn(
        'mb-2 flex max-h-24 cursor-pointer items-center gap-3.5 overflow-hidden rounded-lg border bg-card px-4 py-[13px] transition-colors hover:border-faint',
        selected && 'border-primary/40 bg-primary-soft hover:border-primary/40',
        leaving && 'pointer-events-none animate-row-leave',
      )}
    >
      <span className="w-[18px] flex-none text-right font-mono text-xs text-faint">{index}</span>
      <StateIcon state={d.state} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs">
          <span className="font-mono text-xs text-muted-foreground">{d.id}</span>
          <PriorityDot priority={d.priority} />
          <UrgentTag defect={d} lists={lists} />
          {current && <Tag tone="accent">当前</Tag>}
          {d.state === 'review' && d.needsRecheck && <Tag tone="warn">待复核</Tag>}
          {ghost && <Tag>已移出清单</Tag>}
        </div>
        <div className="my-0.5 truncate text-[14.5px] font-semibold">{d.title}</div>
        <div className="truncate text-xs text-faint">
          {d.type} · {d.requirement}
          {rowExtra(d)}
        </div>
      </div>
      <div className="flex flex-none items-center gap-2">
        {d.state === 'analyzing' && (
          <Button variant="outline" size="icon-sm" title="暂停修复" onClick={stop(() => void actions.pauseDefect(d.id))}>
            <Pause />
          </Button>
        )}
        {d.state === 'paused' && d.pause?.cause !== 'preempted' && listsOf(lists, d.id).length > 0 && (
          <Button variant="outline" size="icon-sm" title="继续修复" onClick={stop(() => void actions.resumeDefect(d.id))}>
            <Play />
          </Button>
        )}
        <StateBadge defect={d} lists={lists} />
      </div>
    </div>
  )
}

/** 清单切换弹层。 */
function ListSwitcher({ list, lists }: { list: DefectList; lists: DefectList[] }) {
  const setViewListId = useUi((s) => s.setViewListId)
  const [open, setOpen] = useState(false)
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        title="切换清单"
        className="inline-flex items-center gap-2 rounded-lg py-0.5 pr-1.5 text-foreground hover:text-primary"
      >
        {list.urgent && <Flame className="size-[22px] text-urgent" />}
        <span className="text-2xl font-bold tracking-[0.2px]">{list.name}</span>
        <ChevronDown className="size-[18px]" />
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={8} className="w-[360px] gap-0 overflow-hidden rounded-lg p-0 pb-1.5 shadow-pop">
        <h5 className="px-3.5 pt-[11px] pb-2 text-xs font-semibold text-faint">选择清单</h5>
        {lists.map((l) => (
          <button
            type="button"
            key={l.id}
            onClick={() => {
              setViewListId(l.id)
              setOpen(false)
            }}
            className="mx-1.5 mb-1 flex w-[calc(100%-12px)] items-center gap-2.5 rounded-md px-2.5 py-[9px] text-left hover:bg-primary-soft"
          >
            <div className="min-w-0 flex-1">
              <b className="block truncate text-[13.5px] font-semibold">{l.name}</b>
              <span className="text-xs text-muted-foreground">{listMeta(l)}</span>
            </div>
            <ListBadge list={l} />
            {l.id === list.id ? <Check className="size-4 text-primary" /> : <i className="w-4 flex-none" />}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  )
}

/** 缺陷页:显示一个清单里的缺陷,按清单顺序平铺并带序号。 */
export function DefectsPage() {
  const { lists, defectMap } = useAppData()
  const viewListId = useUi((s) => s.viewListId)
  const ghosts = useUi((s) => s.ghosts)
  const clearGhosts = useUi((s) => s.clearGhosts)
  const drawerOpen = useUi((s) => s.drawer !== null)
  const detailOpen = useUi((s) => s.drawer?.kind === 'detail')
  const go = useUi((s) => s.go)
  const openEditor = useUi((s) => s.openEditor)
  const openDetail = useUi((s) => s.openDetail)

  // 侧栏关闭后,被移出清单的缺陷淡出,再从列表里消失
  const hasGhosts = Object.keys(ghosts).length > 0
  const leaving = !drawerOpen && hasGhosts
  useEffect(() => {
    if (!leaving) return
    const t = setTimeout(clearGhosts, 480)
    return () => clearTimeout(t)
  }, [leaving, clearGhosts])

  const sorted = [...lists].sort((a, b) => Number(!!b.urgent) - Number(!!a.urgent))
  const list = pickViewList(sorted, viewListId)

  if (!list) {
    return (
      <PageContainer>
        <div className="pt-[30px] pb-[18px]">
          <h1 className="text-2xl font-bold">缺陷</h1>
        </div>
        <EmptyBlock icon={Layers} title="还没有清单" desc="先创建一个清单,把要处理的缺陷放进去。">
          <Button size="lg" onClick={() => go('lists')}>
            去创建清单
          </Button>
        </EmptyBlock>
      </PageContainer>
    )
  }

  const rows = orderWithGhosts(list.defectIds, ghosts)
    .map((id) => defectMap.get(id))
    .filter((d): d is Defect => !!d)
  const mine = list.defectIds.map((id) => defectMap.get(id)).filter((d): d is Defect => !!d)
  const aiDone = mine.filter((d) => !isUndone(d)).length
  const reviews = mine.filter((d) => d.state === 'review')
  const current = firstReview(mine)
  const hasProgress = listHasProgress(mine)
  const active = lists.find((l) => l.state === 'running')
  const paused = pausedHighlight(mine)

  let banner: React.ReactNode = null
  if (list.state === 'pending' && hasProgress && mine.some(isUndone)) {
    banner = (
      <Banner icon={Pause} title={paused ? `已暂停于 ${paused.id} · ${STEPS[paused.step ?? 0]}` : '清单已暂停'} desc={paused ? '进度已保存,继续后会从这里接着处理。' : '继续后会从第一个未处理完的缺陷开始。'}>
        <ListActionButton list={list} hasProgress={hasProgress} size="sm" />
      </Banner>
    )
  } else if (list.state === 'pending' && !list.urgent) {
    banner = (
      <Banner tone="info" icon={Info} title="这个清单还没开始处理" desc={active ? `AI 正在处理「${active.name}」,开始后会排在它后面。` : '开始后,AI 会按下面的顺序逐个修复,不需要你守着。'}>
        <ListActionButton list={list} hasProgress={hasProgress} size="sm" />
      </Banner>
    )
  } else if (list.state === 'queued' && active) {
    banner = (
      <Banner tone="info" icon={Clock} title={`排队中,前面还有「${active.name}」`} desc={active.urgent ? '紧急缺陷优先,处理完会自动恢复这个清单。' : '轮到这个清单时会自动开始。'}>
        {!active.urgent && (
          <Button variant="outline" size="sm" onClick={() => void actions.prioritizeList(list.id)}>
            优先处理这个清单
          </Button>
        )}
      </Banner>
    )
  } else if (list.state === 'done') {
    banner = (
      <Banner tone="ok" icon={Check} title={`AI 已处理完${list.urgent ? '紧急缺陷' : '这个清单'}`} desc={reviews.length ? `还有 ${reviews.length} 个缺陷等你审核。` : '缺陷都已处理完毕。'} />
    )
  }

  return (
    <PageContainer>
      <div className="pt-[30px] pb-[18px]">
        <div className="flex items-start gap-4">
          <div>
            <div className="mb-0.5 flex items-center gap-3">
              <ListSwitcher list={list} lists={sorted} />
              <ListBadge list={list} hasProgress={hasProgress} />
            </div>
            <div className="text-muted-foreground">{list.urgent ? '插队处理,优先于所有清单' : 'AI 会按顺序逐个修复清单里的缺陷,你只需要审核结果'}</div>
          </div>
          <div className="flex-1" />
          {!detailOpen && (
            <span className="inline-flex h-7 items-center gap-1.5 rounded-md bg-subtle px-2.5 text-[12.5px] text-muted-foreground">
              <FolderOpen className="size-3.5" /> mbo-android <GitBranch className="size-3.5" /> main
            </span>
          )}
        </div>
      </div>

      <div className="mb-3 flex flex-wrap items-center gap-2.5">
        <Tag>{list.defectIds.length} 条</Tag>
        <span className="flex-1" />
        {!detailOpen && (
          <div className="flex items-center gap-2 text-[12.5px] text-muted-foreground">
            AI 进度
            <ProgressBar value={mine.length ? (aiDone / mine.length) * 100 : 0} className="w-[120px]" />
            {aiDone} / {mine.length}
          </div>
        )}
        {reviews.length > 0 && current && (
          <Button variant="outline" onClick={() => openDetail(current.id)}>
            去审核
            <Tag tone="soft">{reviews.length}</Tag>
          </Button>
        )}
        {(list.state === 'running' || list.state === 'queued') && <ListActionButton list={list} hasProgress={hasProgress} />}
      </div>

      {banner}

      <div className="mt-1.5">
        {rows.map((d, i) => (
          <DefectRow
            key={d.id}
            defect={d}
            index={i + 1}
            current={d.id === current?.id}
            ghost={d.id in ghosts && !list.defectIds.includes(d.id)}
            leaving={leaving && d.id in ghosts && !list.defectIds.includes(d.id)}
          />
        ))}
      </div>
      {rows.length === 0 &&
        (list.urgent ? (
          <EmptyBlock icon={Flame} title="没有紧急缺陷" desc="遇到要马上处理的缺陷,在详情或搜索结果里点「立即处理」,它就会插队出现在这里。" />
        ) : (
          <EmptyBlock icon={Layers} title="这个清单还是空的" desc="去「清单」页编辑它,或在缺陷详情里把缺陷加进来。">
            <Button variant="outline" onClick={() => openEditor(list.id)}>
              编辑清单
            </Button>
          </EmptyBlock>
        ))}
    </PageContainer>
  )
}


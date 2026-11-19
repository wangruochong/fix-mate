import { ArrowRight, Flame, Layers, Pencil, Plus, TriangleAlert, Trash2 } from 'lucide-react'
import { useAppData } from '@/api/queries'
import { ListBadge } from '@/components/common/defect-bits'
import { Banner, EmptyBlock, Spinner } from '@/components/common/feedback'
import { ListActionButton } from '@/components/list-action'
import { PageContainer, PageHeader } from '@/components/page'
import { Button } from '@/components/ui/button'
import { shortDate } from '@/lib/format'
import { isUndone, type Defect, type DefectState } from '@/types/defect'
import type { DefectList } from '@/types/list'
import { listHasProgress } from '@/lib/defect'
import { listedIds } from '@/lib/list-editor'
import { useUi } from '@/store/ui'
import { cn } from 'cn'

type Segment = { count: number; color: string; label: string }

/** 进度条的分段:接受、拒绝、跳过、待审核、未处理。 */
function segments(ds: Defect[]): Segment[] {
  const n = (s: DefectState) => ds.filter((d) => d.state === s).length
  return [
    { count: n('accepted'), color: 'var(--success)', label: '接受' },
    { count: n('rejected'), color: 'var(--destructive)', label: '拒绝' },
    { count: n('passed'), color: 'var(--faint)', label: '跳过' },
    { count: n('review'), color: 'var(--primary)', label: '待审核' },
    { count: ds.filter(isUndone).length, color: 'color-mix(in srgb, var(--primary) 28%, var(--border))', label: '未处理' },
  ]
}

function ListCard({ list, defectMap }: { list: DefectList; defectMap: Map<string, Defect> }) {
  const viewList = useUi((s) => s.viewList)
  const openEditor = useUi((s) => s.openEditor)
  const openDialog = useUi((s) => s.openDialog)

  const ds = list.defectIds.map((id) => defectMap.get(id)).filter((d): d is Defect => !!d)
  const segs = segments(ds)
  const pending = segs[4].count
  const review = segs[3].count
  const stop = (e: React.MouseEvent) => e.stopPropagation()

  return (
    <div
      role="button"
      tabIndex={0}
      title={`查看「${list.name}」中的缺陷`}
      onClick={() => viewList(list.id)}
      onKeyDown={(e) => e.key === 'Enter' && viewList(list.id)}
      className={cn(
        'group relative flex cursor-pointer flex-col gap-2.5 rounded-xl border bg-card p-[18px] outline-none transition-all duration-150',
        'hover:-translate-y-0.5 hover:border-primary/45 hover:shadow-pop focus-visible:ring-3 focus-visible:ring-ring/30',
        list.state === 'running' && 'border-primary/50 shadow-[0_0_0_3px_var(--primary-soft)]',
        list.urgent && 'border-urgent/45 bg-gradient-to-b from-urgent-soft to-card to-75% hover:border-urgent',
      )}
    >
      <ArrowRight className="absolute top-[19px] right-[18px] size-[18px] text-faint transition-all duration-200 group-hover:translate-x-1 group-hover:text-primary" />
      <div className="flex min-w-0 items-center gap-2 pr-[30px] text-base">
        {list.urgent && <Flame className="size-[17px] shrink-0 text-urgent" />}
        <b className="truncate font-semibold">{list.name}</b>
        <ListBadge list={list} hasProgress={listHasProgress(ds)} />
      </div>
      <div className="text-[13px] text-muted-foreground">
        {list.defectIds.length} 个缺陷 · {list.urgent ? '插队处理' : `创建于 ${shortDate(list.createdAt)}`}
      </div>
      <div className="flex h-1.5 gap-0.5 overflow-hidden rounded-[3px] bg-subtle">
        {segs.map((s) => s.count > 0 && <i key={s.label} className="block h-full" style={{ flex: s.count, background: s.color }} />)}
      </div>
      <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
        {segs
          .filter((s) => s.count > 0)
          .map((s) => (
            <span key={s.label}>
              <i className="mr-[5px] inline-block size-[7px] rounded-full" style={{ background: s.color }} />
              {s.label} {s.count}
            </span>
          ))}
      </div>
      <div className="mt-1 flex items-center gap-1.5 border-t pt-3">
        <span className="text-[12.5px] text-muted-foreground">
          AI 已处理 {ds.length - pending} / {ds.length}
          {review > 0 && (
            <>
              {' · '}
              <b className="font-semibold text-primary-text">{review} 个待审核</b>
            </>
          )}
        </span>
        <span className="flex-1" />
        {!list.urgent && (
          <>
            <Button variant="ghost" size="icon" title="编辑清单" aria-label="编辑清单" onClick={(e) => { stop(e); openEditor(list.id) }}>
              <Pencil className="size-[15px]!" />
            </Button>
            <Button variant="ghost" size="icon" title="删除清单" aria-label="删除清单" onClick={(e) => { stop(e); openDialog({ kind: 'deleteList', listId: list.id }) }}>
              <Trash2 className="size-[15px]!" />
            </Button>
          </>
        )}
        <ListActionButton list={list} hasProgress={listHasProgress(ds)} size="sm" />
      </div>
    </div>
  )
}

export function ListsPage() {
  const { defects, lists, defectMap, isPending } = useAppData()
  const openEditor = useUi((s) => s.openEditor)

  if (isPending) {
    return (
      <PageContainer>
        <div className="grid place-items-center py-32">
          <Spinner className="size-6" />
        </div>
      </PageContainer>
    )
  }

  const listed = listedIds(lists)
  const unlisted = defects.filter((d) => !listed.has(d.id)).length

  return (
    <PageContainer>
      <PageHeader title="清单" desc="把要处理的缺陷分组,点开清单即可查看并开始处理">
        <Button size="lg" onClick={() => openEditor()}>
          <Plus />
          新建清单
        </Button>
      </PageHeader>
      {unlisted > 0 && (
        <Banner icon={TriangleAlert} title={`有 ${unlisted} 个缺陷还没加入任何清单`} desc="不在清单里的缺陷不会被自动处理,建议尽快归类。">
          <Button size="sm" variant="outline" onClick={() => openEditor(undefined, 'unlisted')}>
            一键新建清单
          </Button>
        </Banner>
      )}
      {lists.length > 0 ? (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-3.5">
          {lists.map((l) => (
            <ListCard key={l.id} list={l} defectMap={defectMap} />
          ))}
          <button
            type="button"
            onClick={() => openEditor()}
            className="flex min-h-[176px] flex-col items-center justify-center gap-2 rounded-xl border-[1.5px] border-dashed font-medium text-muted-foreground transition-colors hover:border-primary hover:bg-primary-soft hover:text-primary"
          >
            <Plus className="size-[22px]" />
            <span>新建清单</span>
          </button>
        </div>
      ) : (
        <EmptyBlock icon={Layers} title="还没有任何清单" desc="新建一个清单,挑选要让 AI 处理的缺陷。">
          <Button size="lg" onClick={() => openEditor()}>
            新建清单
          </Button>
        </EmptyBlock>
      )}
    </PageContainer>
  )
}

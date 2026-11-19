import { Search } from 'lucide-react'
import { useAppData } from '@/api/queries'
import { EmptyBlock } from '@/components/common/feedback'
import { ListChips, PriorityDot, StateBadge, StateIcon, UrgentTag } from '@/components/common/defect-bits'
import { PageContainer, PageHeader } from '@/components/page'
import { Button } from '@/components/ui/button'
import { UrgentButton } from '@/components/urgent-button'
import { searchDefects } from '@/lib/defect'
import { useUi } from '@/store/ui'
import { cn } from 'cn'

/** 搜索页:按标题模糊搜索全部缺陷,不限于清单。 */
export function SearchPage() {
  const { defects, lists } = useAppData()
  const query = useUi((s) => s.searchQuery)
  const searched = useUi((s) => s.searchedQuery)
  const setQuery = useUi((s) => s.setSearchQuery)
  const runSearch = useUi((s) => s.runSearch)
  const openDetail = useUi((s) => s.openDetail)
  const selectedId = useUi((s) => (s.drawer?.kind === 'detail' ? s.drawer.defectId : null))
  const results = searchDefects(defects, searched)

  return (
    <PageContainer>
      <PageHeader title="搜索" desc="按标题模糊搜索全部缺陷,不限于清单" />
      <div className="mb-2.5 flex gap-2.5">
        <label className="flex h-11 flex-1 items-center gap-2.5 rounded-lg border bg-card px-3.5 text-faint focus-within:border-primary focus-within:ring-3 focus-within:ring-primary-soft">
          <Search className="size-[18px]" />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && runSearch()}
            placeholder="输入缺陷标题的关键词,例如「登录」"
            className="flex-1 bg-transparent text-foreground outline-none"
          />
        </label>
        <Button size="lg" onClick={runSearch}>
          搜索
        </Button>
      </div>

      {!searched ? (
        <EmptyBlock icon={Search} title="搜索任意缺陷" desc="输入标题关键词,找到后点开即可查看详情,或把它加入清单。" />
      ) : results.length === 0 ? (
        <EmptyBlock icon={Search} title="没有找到相关缺陷" desc={`没有标题匹配「${searched}」的缺陷,换个关键词试试。`} />
      ) : (
        <>
          <div className="mt-3.5 mb-2.5 px-1 text-[12.5px] text-muted-foreground">
            找到 {results.length} 个匹配「{searched}」的缺陷
          </div>
          {results.map((d) => (
            <div
              key={d.id}
              role="button"
              tabIndex={0}
              onClick={() => openDetail(d.id)}
              onKeyDown={(e) => e.key === 'Enter' && openDetail(d.id)}
              className={cn(
                'mb-2 flex cursor-pointer items-center gap-3.5 overflow-hidden rounded-lg border bg-card px-4 py-[13px] transition-colors hover:border-faint',
                selectedId === d.id && 'border-primary/40 bg-primary-soft hover:border-primary/40',
              )}
            >
              <StateIcon state={d.state} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-xs">
                  <span className="font-mono text-xs text-muted-foreground">{d.id}</span>
                  <PriorityDot priority={d.priority} />
                  <UrgentTag defect={d} lists={lists} />
                </div>
                <div className="my-0.5 truncate text-[14.5px] font-semibold">{d.title}</div>
                <div className="truncate text-xs text-faint">
                  {d.type} · {d.requirement}
                </div>
              </div>
              <div className="flex flex-none items-center gap-2">
                <UrgentButton defect={d} />
                <ListChips lists={lists} defectId={d.id} />
                <StateBadge defect={d} lists={lists} />
              </div>
            </div>
          ))}
        </>
      )}
    </PageContainer>
  )
}

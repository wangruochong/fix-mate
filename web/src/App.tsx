import { useEffect } from 'react'
import { useAppData } from '@/api/queries'
import { Spinner } from '@/components/common/feedback'
import { Toaster } from '@/components/ui/sonner'
import { USE_MOCK } from '@/config'
import { AcceptDialog } from '@/dialogs/accept-dialog'
import { DeleteListDialog } from '@/dialogs/delete-list-dialog'
import { PassDialog } from '@/dialogs/pass-dialog'
import { RejectDialog } from '@/dialogs/reject-dialog'
import { UrgentDialog } from '@/dialogs/urgent-dialog'
import { DetailDrawer } from '@/drawers/detail-drawer'
import { ListEditor } from '@/drawers/list-editor'
import { DebugPanel } from '@/layout/debug-panel'
import { Rail } from '@/layout/rail'
import { UrgentBar } from '@/layout/urgent-bar'
import { DefectsPage } from '@/pages/defects-page'
import { ListsPage } from '@/pages/lists-page'
import { SearchPage } from '@/pages/search-page'
import { OnboardPage, SettingsPage } from '@/pages/settings-page'
import { pickViewList } from '@/lib/work'
import { useUi } from '@/store/ui'

const PAGES = { work: DefectsPage, lists: ListsPage, search: SearchPage, settings: SettingsPage, onboard: OnboardPage }

export default function App() {
  const view = useUi((s) => s.view)
  const { lists, isPending, isError, error } = useAppData()
  const viewListId = useUi((s) => s.viewListId)
  const setViewListId = useUi((s) => s.setViewListId)
  const Page = PAGES[view]

  // 缺陷页首次显示时固定住当前清单,之后不会因为别的清单开始处理而自动切换
  useEffect(() => {
    if (viewListId !== null || lists.length === 0) return
    const sorted = [...lists].sort((a, b) => Number(!!b.urgent) - Number(!!a.urgent))
    setViewListId(pickViewList(sorted, null)?.id ?? null)
  }, [viewListId, lists, setViewListId])

  // 切换页面时回到顶部
  useEffect(() => {
    document.getElementById('page-scroll')?.scrollTo({ top: 0 })
  }, [view])

  if (isPending) {
    return (
      <div className="grid h-full place-items-center">
        <Spinner className="size-6" />
      </div>
    )
  }
  if (isError) {
    return (
      <div className="grid h-full place-items-center text-center text-muted-foreground">
        <div>
          <h2 className="mb-1.5 text-[17px] font-semibold text-foreground">连接不上服务</h2>
          <p>{error instanceof Error ? error.message : '请检查后端是否已启动。'}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex h-screen">
      {view !== 'onboard' && <Rail />}
      <div className="flex min-w-0 flex-1 flex-col">
        {view !== 'onboard' && <UrgentBar />}
        <main id="page-scroll" className="flex-1 overflow-auto">
          <Page />
        </main>
      </div>
      <DetailDrawer />
      <ListEditor />
      <AcceptDialog />
      <RejectDialog />
      <PassDialog />
      <UrgentDialog />
      <DeleteListDialog />
      <Toaster />
      {USE_MOCK && <DebugPanel />}
    </div>
  )
}

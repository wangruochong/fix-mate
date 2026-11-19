import { create } from 'zustand'

export type View = 'work' | 'lists' | 'search' | 'settings' | 'onboard'

export type DrawerState =
  | { kind: 'detail'; defectId: string }
  | { kind: 'edit'; listId?: string; preset?: 'unlisted' }
  | null

export type DialogState =
  | { kind: 'accept' | 'reject' | 'pass' | 'urgent'; defectId: string }
  | { kind: 'deleteList'; listId: string }
  | null

export interface AcceptProgress {
  step: number
  ota?: string
}

/** 纯界面状态。业务数据都来自接口,不放在这里。 */
interface UiState {
  view: View
  /** 缺陷页正在查看的清单 */
  viewListId: string | null
  drawer: DrawerState
  dialog: DialogState
  searchQuery: string
  /** 已搜索过的关键词;为空表示还没搜索 */
  searchedQuery: string
  /** 从当前查看的清单中移除、但侧栏关闭前仍保留显示的缺陷:id -> 原位置 */
  ghosts: Record<string, number>
  /** 接受流程的进度,由 SSE 事件更新 */
  acceptProgress: Record<string, AcceptProgress>

  go: (view: View) => void
  /** 在缺陷页查看某个清单 */
  viewList: (listId: string) => void
  setViewListId: (listId: string | null) => void
  openDetail: (defectId: string) => void
  openEditor: (listId?: string, preset?: 'unlisted') => void
  closeDrawer: () => void
  openDialog: (dialog: NonNullable<DialogState>) => void
  closeDialog: () => void
  setSearchQuery: (q: string) => void
  runSearch: () => void
  addGhost: (defectId: string, index: number) => void
  clearGhosts: () => void
  setAcceptProgress: (defectId: string, p: AcceptProgress) => void
  clearAcceptProgress: (defectId: string) => void
}

export const useUi = create<UiState>((set) => ({
  view: 'work',
  viewListId: null,
  drawer: null,
  dialog: null,
  searchQuery: '',
  searchedQuery: '',
  ghosts: {},
  acceptProgress: {},

  // 侧栏开着时不允许切换页面,与原型一致
  go: (view) => set((s) => (s.drawer ? s : { view })),
  viewList: (listId) => set({ viewListId: listId, ghosts: {}, view: 'work' }),
  setViewListId: (listId) => set({ viewListId: listId, ghosts: {} }),
  openDetail: (defectId) => set({ drawer: { kind: 'detail', defectId } }),
  openEditor: (listId, preset) => set({ drawer: { kind: 'edit', listId, preset } }),
  closeDrawer: () => set({ drawer: null }),
  openDialog: (dialog) => set({ dialog }),
  closeDialog: () => set({ dialog: null }),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  runSearch: () => set((s) => ({ searchedQuery: s.searchQuery.trim() })),
  addGhost: (defectId, index) => set((s) => ({ ghosts: { ...s.ghosts, [defectId]: index } })),
  clearGhosts: () => set({ ghosts: {} }),
  setAcceptProgress: (defectId, p) => set((s) => ({ acceptProgress: { ...s.acceptProgress, [defectId]: p } })),
  clearAcceptProgress: (defectId) =>
    set((s) => {
      const { [defectId]: _, ...rest } = s.acceptProgress
      return { acceptProgress: rest }
    }),
}))

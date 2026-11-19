import { toast } from 'sonner'
import { api } from './client'
import { queryClient } from './queryClient'

/** 发出请求并刷新数据;失败时弹出错误提示。 */
async function call<T = unknown>(path: string, method: 'POST' | 'PATCH' | 'DELETE' = 'POST', body?: unknown) {
  try {
    const res = await api<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) })
    void queryClient.invalidateQueries()
    return res
  } catch (e) {
    toast.error(e instanceof Error ? e.message : '操作失败')
    throw e
  }
}

export interface ListInput {
  name: string
  defectIds: string[]
}

/** 所有会改变后端状态的操作。业务规则都在后端,这里只负责发请求。 */
export const actions = {
  startList: (id: string) => call(`/lists/${id}/start`),
  pauseList: (id: string) => call(`/lists/${id}/pause`),
  prioritizeList: (id: string) => call(`/lists/${id}/prioritize`),
  createList: (input: ListInput) => call<{ id: string }>('/lists', 'POST', input),
  updateList: (id: string, input: ListInput) => call(`/lists/${id}`, 'PATCH', input),
  deleteList: (id: string) => call(`/lists/${id}`, 'DELETE'),
  addToList: (listId: string, defectId: string) => call(`/lists/${listId}/defects`, 'POST', { defectId }),
  removeFromList: (listId: string, defectId: string) => call(`/lists/${listId}/defects/${defectId}`, 'DELETE'),

  pauseDefect: (id: string) => call(`/defects/${id}/pause`),
  resumeDefect: (id: string) => call(`/defects/${id}/resume`),
  setUrgent: (id: string, position: 'front' | 'back') => call(`/defects/${id}/urgent`, 'POST', { position }),
  recheck: (id: string) => call(`/defects/${id}/recheck`),
  accept: (id: string) => call(`/defects/${id}/accept`),
  reject: (id: string, input: { keepChanges: boolean; reason?: string }) => call(`/defects/${id}/reject`, 'POST', input),
  pass: (id: string, reason: string) => call(`/defects/${id}/pass`, 'POST', { reason }),

  markNotificationsRead: () => call('/notifications/read'),

  /** 开发调试,只在假接口下可用 */
  dev: {
    newDefect: () => call('/dev/new-defect'),
    bulk: (count: number) => call('/dev/bulk', 'POST', { count }),
    reset: () => call('/dev/reset'),
  },
}

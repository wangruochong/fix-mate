import { showToast } from '@/lib/toast'
import { useUi } from '@/store/ui'
import type { ServerEvent } from '@/types/events'
import { queryClient } from './queryClient'

const BASE_URL = import.meta.env.VITE_API_BASE ?? ''

/** 订阅后端事件流:数据变化时刷新、弹出提示、更新接受进度。返回取消订阅的函数。 */
export function connectEvents() {
  const source = new EventSource(`${BASE_URL}/api/events`)
  source.onmessage = (msg) => {
    const e = JSON.parse(msg.data as string) as ServerEvent
    switch (e.type) {
      case 'changed':
        void queryClient.invalidateQueries()
        break
      case 'toast':
        showToast(e)
        break
      case 'accept-progress':
        useUi.getState().setAcceptProgress(e.defectId, { step: e.step, ota: e.ota })
        break
    }
  }
  return () => source.close()
}

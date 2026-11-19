export type NotificationKind = 'new' | 'ok' | 'skip' | 'done' | 'warn'

export interface AppNotification {
  id: string
  title: string
  body: string
  kind: NotificationKind
  defectId?: string
  unread: boolean
  createdAt: string
}

/** 后端通过 SSE 推送的事件。数据变化统一用 changed 通知前端重新获取。 */
export type ServerEvent =
  | { type: 'changed' }
  | { type: 'toast'; title: string; body: string; kind: NotificationKind; defectId?: string; quiet: boolean }
  | { type: 'accept-progress'; defectId: string; step: number; ota?: string; error?: string }

import { queryOptions, useQuery } from '@tanstack/react-query'
import { useMemo } from 'react'
import type { Defect } from '@/types/defect'
import type { AppNotification } from '@/types/events'
import type { DefectList } from '@/types/list'
import { api } from './client'

export const defectsQuery = queryOptions({
  queryKey: ['defects'],
  queryFn: () => api<Defect[]>('/defects'),
})

export const listsQuery = queryOptions({
  queryKey: ['lists'],
  queryFn: () => api<DefectList[]>('/lists'),
})

export const notificationsQuery = queryOptions({
  queryKey: ['notifications'],
  queryFn: () => api<AppNotification[]>('/notifications'),
})

export const useDefects = () => useQuery(defectsQuery)
export const useLists = () => useQuery(listsQuery)
export const useNotifications = () => useQuery(notificationsQuery)

/** 缺陷和清单一起取,页面里几乎总是两者都要。 */
export function useAppData() {
  const defects = useQuery(defectsQuery)
  const lists = useQuery(listsQuery)
  const defectMap = useMemo(() => new Map((defects.data ?? []).map((d) => [d.id, d])), [defects.data])
  return {
    defects: defects.data ?? [],
    lists: lists.data ?? [],
    defectMap,
    isPending: defects.isPending || lists.isPending,
    isError: defects.isError || lists.isError,
    error: defects.error ?? lists.error,
  }
}

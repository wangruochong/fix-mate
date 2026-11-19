import { QueryClient } from '@tanstack/react-query'

/** 数据变化由后端通过 SSE 通知后再刷新,所以不需要自动过期和失焦刷新。 */
export const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: Infinity, refetchOnWindowFocus: false, retry: false } },
})

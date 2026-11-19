const MIN = 60_000

/** 相对时间:刚刚、N 分钟前、N 小时前、昨天、N 天前。 */
export function timeAgo(iso: string, now = Date.now()) {
  const diff = now - new Date(iso).getTime()
  if (diff < MIN) return '刚刚'
  if (diff < 60 * MIN) return `${Math.floor(diff / MIN)} 分钟前`
  if (diff < 24 * 60 * MIN) return `${Math.floor(diff / (60 * MIN))} 小时前`
  if (diff < 48 * 60 * MIN) return '昨天'
  return `${Math.floor(diff / (24 * 60 * MIN))} 天前`
}

/** 时分,如 14:05。 */
export const clock = (iso: string) =>
  new Date(iso).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })

/** 月-日,如 11-02。 */
export const shortDate = (iso: string) => {
  const d = new Date(iso)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

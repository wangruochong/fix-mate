import { Pause, Play } from 'lucide-react'
import { actions } from '@/api/actions'
import type { DefectList } from '@/types/list'
import { Button } from '@/components/ui/button'

/**
 * 清单的开始、继续、暂停按钮。
 * 待处理且没有进度显示「开始处理」,有进度显示「继续处理」;处理中或排队中显示「暂停处理」;
 * 紧急清单和处理完成的清单没有按钮。
 */
export function ListActionButton({ list, hasProgress, size }: { list: DefectList; hasProgress: boolean; size?: 'sm' | 'default' }) {
  if (list.urgent) return null
  const stop = (e: React.MouseEvent) => e.stopPropagation()
  if (list.state === 'pending') {
    return (
      <Button size={size} onClick={(e) => { stop(e); void actions.startList(list.id) }}>
        <Play />
        {hasProgress ? '继续处理' : '开始处理'}
      </Button>
    )
  }
  if (list.state === 'running' || list.state === 'queued') {
    return (
      <Button variant="outline" size={size} onClick={(e) => { stop(e); void actions.pauseList(list.id) }}>
        <Pause />
        暂停处理
      </Button>
    )
  }
  return null
}

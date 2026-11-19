import { useState } from 'react'
import { actions } from '@/api/actions'
import { useAppData } from '@/api/queries'
import { Note } from '@/components/common/feedback'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { shortDate } from '@/lib/format'
import { useUi } from '@/store/ui'
import type { DefectList } from '@/types/list'

/** 删除清单前的确认。缺陷本身不会被删除。 */
export function DeleteListDialog() {
  const dialog = useUi((s) => s.dialog)
  const closeDialog = useUi((s) => s.closeDialog)
  const { lists } = useAppData()
  // 关闭动画期间清单可能已经被删掉,保留最后一次看到的清单用来显示
  const [last, setLast] = useState<DefectList | undefined>()

  const open = dialog?.kind === 'deleteList'
  const target = open ? lists.find((l) => l.id === dialog.listId) : undefined
  if (target && target !== last) setLast(target)
  const list = target ?? last

  const onlyHere = list ? list.defectIds.filter((id) => lists.filter((l) => l.defectIds.includes(id)).length === 1).length : 0

  async function confirm() {
    if (!list) return
    const { viewListId, setViewListId } = useUi.getState()
    const others = lists.filter((l) => l.id !== list.id)
    try {
      await actions.deleteList(list.id)
    } catch {
      return
    }
    if (viewListId === list.id) setViewListId((others.find((l) => l.state === 'running') ?? others[0])?.id ?? null)
    closeDialog()
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && closeDialog()}>
      <DialogContent className="sm:max-w-[520px]" showCloseButton={false}>
        {list && (
          <>
            <DialogHeader>
              <DialogTitle className="text-[17px]">删除清单「{list.name}」?</DialogTitle>
              <DialogDescription>
                {list.urgent ? `${list.defectIds.length} 个缺陷 · 插队处理` : `${list.defectIds.length} 个缺陷 · 创建于 ${shortDate(list.createdAt)}`}
                。缺陷本身不会被删除。
              </DialogDescription>
            </DialogHeader>
            {onlyHere > 0 && <Note className="mt-0">其中 {onlyHere} 个缺陷只属于这个清单,删除后它们会变成「未入清单」。</Note>}
            {list.state === 'running' && <Note className="mt-0">这个清单正在处理中,删除后正在修复的缺陷会被暂停并保存进度。</Note>}
            <DialogFooter className="-mx-4 -mb-4 border-t-0 bg-transparent">
              <Button variant="outline" onClick={closeDialog}>
                取消
              </Button>
              <Button variant="danger" onClick={() => void confirm()}>
                确认删除
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  )
}

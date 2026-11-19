import { AlertTriangle, Layers, Minus, Plus } from 'lucide-react'
import { useState } from 'react'
import { actions } from '@/api/actions'
import { Tag } from '@/components/common/tag'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { listsOf } from '@/lib/defect'
import { shortDate } from '@/lib/format'
import { useUi } from '@/store/ui'
import type { Defect } from '@/types/defect'
import type { DefectList } from '@/types/list'

const listMeta = (l: DefectList) => (l.urgent ? `${l.defectIds.length} 个缺陷 · 插队处理` : `${l.defectIds.length} 个缺陷 · 创建于 ${shortDate(l.createdAt)}`)

/** 缺陷所属清单:不在任何清单时提示并可添加;在清单里时可从清单删除。 */
export function ListBox({ defect, lists }: { defect: Defect; lists: DefectList[] }) {
  const mine = listsOf(lists, defect.id)
  if (!mine.length) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-warning/30 bg-warning-soft px-[15px] py-3">
        <AlertTriangle className="size-5 text-warning" />
        <div className="min-w-0 flex-1">
          <b className="block text-[13px]">还不在任何清单中</b>
          <span className="text-xs text-muted-foreground">不在清单里的缺陷不会被自动处理</span>
        </div>
        <ListPicker mode="add" defect={defect} lists={lists} />
      </div>
    )
  }
  return (
    <div className="flex items-center gap-3 rounded-lg border bg-card px-[15px] py-3">
      <Layers className="size-5 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <b className="block text-[13px]">所属清单</b>
        <div className="mt-1.5 flex flex-wrap gap-[7px]">
          {mine.map((l) => (
            <Tag key={l.id} tone="list" className="max-w-[200px]" title={l.name}>
              {l.name}
            </Tag>
          ))}
        </div>
      </div>
      <ListPicker mode="remove" defect={defect} lists={lists} />
    </div>
  )
}

/** 选择清单的弹层:add 列出还没加入的清单,remove 列出已加入的清单。 */
function ListPicker({ mode, defect, lists }: { mode: 'add' | 'remove'; defect: Defect; lists: DefectList[] }) {
  const [open, setOpen] = useState(false)
  const options = mode === 'add' ? lists.filter((l) => !l.urgent && !l.defectIds.includes(defect.id)) : listsOf(lists, defect.id)

  const pick = (l: DefectList) => {
    setOpen(false)
    if (mode === 'add') {
      void actions.addToList(l.id, defect.id)
      return
    }
    const { viewListId, view, addGhost } = useUi.getState()
    // 从正在查看的清单里删除时,先保留一行,侧栏关闭后再消失
    if (l.id === viewListId && view === 'work') addGhost(defect.id, l.defectIds.indexOf(defect.id))
    void actions.removeFromList(l.id, defect.id)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          mode === 'add' ? (
            <Button size="sm">
              <Plus />
              添加到清单
            </Button>
          ) : (
            <Button size="sm" variant="danger">
              <Minus />
              从清单中删除
            </Button>
          )
        }
      />
      <PopoverContent align="end" sideOffset={8} className="w-[340px] gap-0 overflow-hidden rounded-lg p-0 pb-1.5 shadow-pop">
        <h5 className="px-3.5 pt-[11px] pb-2 text-xs font-semibold text-faint">
          {mode === 'add' ? '添加到哪个清单' : '从哪个清单中删除'}
        </h5>
        {options.length ? (
          options.map((l) => (
            <button
              key={l.id}
              type="button"
              onClick={() => pick(l)}
              className="mx-1.5 mb-1 flex w-[calc(100%-12px)] items-center gap-2.5 rounded-md px-2.5 py-[9px] text-left hover:bg-primary-soft"
            >
              <div className="min-w-0 flex-1">
                <b className="block truncate text-[13.5px] font-semibold">{l.name}</b>
                <span className="text-xs text-muted-foreground">{listMeta(l)}</span>
              </div>
              {mode === 'add' ? <Plus className="size-4 text-faint" /> : <Minus className="size-4 text-faint" />}
            </button>
          ))
        ) : (
          <div className="px-3.5 pt-2.5 pb-3.5 text-[13px] text-faint">还没有清单,请先到「清单」页新建。</div>
        )}
      </PopoverContent>
    </Popover>
  )
}

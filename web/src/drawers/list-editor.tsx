import { Check, ChevronDown, ChevronUp, Filter, Info, X } from 'lucide-react'
import { cn } from 'cn'
import { memo, useMemo, useRef, useState } from 'react'
import { actions } from '@/api/actions'
import { useAppData } from '@/api/queries'
import { PriorityDot, ListChips } from '@/components/common/defect-bits'
import { EmptyBlock, Hint, Mono } from '@/components/common/feedback'
import { Switch } from '@/components/common/switch'
import { Tag } from '@/components/common/tag'
import { Drawer } from '@/components/drawer'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { DEFECT_TYPES, fuzzy, PRIORITIES, PRIORITY_COLOR } from '@/lib/defect'
import {
  distinctValues,
  emptyFilter,
  filterCount,
  filterDefects,
  hiddenSelectedCount,
  listedIds,
  selectAllVisible,
  toggleItem,
  type EditorFilter,
} from '@/lib/list-editor'
import { useUi, type DrawerState } from '@/store/ui'
import type { Defect, DefectType, Priority } from '@/types/defect'
import type { DefectList } from '@/types/list'

type EditDrawer = Extract<NonNullable<DrawerState>, { kind: 'edit' }>

/**
 * 新建 / 编辑清单的右侧侧栏。
 * 每次打开都重新挂载内容,这样输入、筛选和已选状态不会带到下一次。
 */
export function ListEditor() {
  const drawer = useUi((s) => s.drawer)
  const closeDrawer = useUi((s) => s.closeDrawer)
  const open = drawer?.kind === 'edit' ? drawer : null
  // 关闭动画期间内容还要继续显示,所以保留最近一次打开时的参数
  const [snap, setSnap] = useState<{ params: EditDrawer; session: number } | null>(null)

  // 每次打开(参数对象变了)就开一个新的会话,让内容重新挂载
  if (open && snap?.params !== open) setSnap({ params: open, session: (snap?.session ?? 0) + 1 })

  if (!snap) return null
  return (
    <Drawer open={!!open && open === snap.params} onClose={closeDrawer}>
      <EditorBody key={snap.session} params={snap.params} onClose={closeDrawer} />
    </Drawer>
  )
}

function EditorBody({ params, onClose }: { params: EditDrawer; onClose: () => void }) {
  const { defects, lists } = useAppData()
  const editing = params.listId ? lists.find((l) => l.id === params.listId) : undefined

  const [name, setName] = useState(() => editing?.name ?? (params.preset === 'unlisted' ? '未归类缺陷' : ''))
  const [selected, setSelected] = useState<ReadonlySet<string>>(() => {
    if (editing) return new Set(editing.defectIds)
    if (params.preset === 'unlisted') {
      const listed = listedIds(lists)
      return new Set(defects.filter((d) => !listed.has(d.id)).map((d) => d.id))
    }
    return new Set()
  })
  const [filter, setFilter] = useState<EditorFilter>(emptyFilter)
  const [filterOpen, setFilterOpen] = useState(true)
  const [nameError, setNameError] = useState(0)
  const [saving, setSaving] = useState(false)
  const nameRef = useRef<HTMLInputElement>(null)

  const visible = useMemo(() => filterDefects(defects, filter, lists), [defects, filter, lists])
  const hidden = hiddenSelectedCount(selected, visible)
  const count = filterCount(filter)

  async function save() {
    const trimmed = name.trim()
    if (!trimmed) {
      setNameError((n) => n + 1)
      nameRef.current?.focus()
      return
    }
    setSaving(true)
    try {
      const input = { name: trimmed, defectIds: [...selected] }
      if (editing) await actions.updateList(editing.id, input)
      else await actions.createList(input)
      onClose()
    } catch {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="flex flex-none items-center gap-2.5 border-b px-[22px] py-[15px]">
        <h2 className="text-[17px] font-semibold">{editing ? '编辑清单' : '新建清单'}</h2>
        <span className="flex-1" />
        <Button variant="ghost" size="icon" onClick={onClose} title="关闭 (Esc)" aria-label="关闭">
          <X />
        </Button>
      </div>

      <div className="flex-none px-[22px] pt-[18px] pb-3.5">
        <label htmlFor="list-name" className="mb-[7px] block text-xs font-semibold text-muted-foreground">
          清单名称
        </label>
        <Input
          key={nameError}
          id="list-name"
          ref={nameRef}
          maxLength={40}
          value={name}
          placeholder="例如:本周必修、登录相关"
          aria-invalid={nameError > 0 && !name.trim()}
          onChange={(e) => setName(e.target.value)}
          className={cn('h-9 rounded-md bg-card px-3 text-sm md:text-sm dark:bg-card', nameError > 0 && !name.trim() && 'animate-shake')}
        />
        {nameError > 0 && !name.trim() && <div className="mt-1.5 text-xs text-danger">请先给清单起个名字</div>}
        <Hint className="mt-1.5">
          <Info className="mt-px size-[13px] shrink-0" />
          名称可以重复,方便你按习惯命名。
        </Hint>
      </div>

      <FilterPanel
        filter={filter}
        onChange={setFilter}
        open={filterOpen}
        onToggleOpen={() => setFilterOpen((o) => !o)}
        defects={defects}
        count={count}
      />

      <div className="flex flex-none items-center gap-2 border-b px-[22px] py-[11px] text-[13px]">
        <Button size="sm" variant="outline" onClick={() => setSelected((s) => selectAllVisible(s, visible))}>
          全选
        </Button>
        <Button size="sm" variant="outline" onClick={() => setSelected(new Set())}>
          清空
        </Button>
        <span className="ml-1.5">
          <b>已选 {selected.size} 条</b>
          {hidden > 0 && <span className="text-faint"> · 其中 {hidden} 条被筛选隐藏</span>}
        </span>
        <span className="flex-1" />
        <span className="text-xs text-faint">符合筛选 {visible.length} 条</span>
      </div>

      <div className="min-h-0 flex-1 overflow-auto px-3.5 py-2">
        {visible.length ? (
          visible.map((d) => (
            <EditorRow
              key={d.id}
              defect={d}
              lists={lists}
              checked={selected.has(d.id)}
              onToggle={(id) => setSelected((s) => toggleItem(s, id))}
            />
          ))
        ) : (
          <EmptyBlock icon={Filter} title="没有符合条件的缺陷" desc="调整上方的筛选条件试试。" />
        )}
      </div>

      <div className="flex flex-none items-center gap-2.5 border-t bg-card px-[22px] py-3.5">
        <span className="flex-1" />
        <Button variant="outline" onClick={onClose}>
          取消
        </Button>
        <Button size="lg" disabled={selected.size === 0 || saving} onClick={() => void save()}>
          {editing ? '保存修改' : '保存清单'} · {selected.size} 条
        </Button>
      </div>
    </>
  )
}

/** 缺陷列表里的一行,可勾选。用 memo 避免勾选一项时整张列表重绘。 */
const EditorRow = memo(function EditorRow({
  defect: d,
  lists,
  checked,
  onToggle,
}: {
  defect: Defect
  lists: DefectList[]
  checked: boolean
  onToggle: (id: string) => void
}) {
  return (
    <div
      role="checkbox"
      aria-checked={checked}
      tabIndex={0}
      onClick={() => onToggle(d.id)}
      onKeyDown={(e) => {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault()
          onToggle(d.id)
        }
      }}
      className={cn(
        'flex cursor-pointer items-center gap-3 rounded-md p-2.5 outline-none hover:bg-panel-2 focus-visible:ring-3 focus-visible:ring-ring/30',
        checked && 'bg-primary-soft hover:bg-primary-soft',
      )}
    >
      <span
        className={cn(
          'grid size-[18px] shrink-0 place-items-center rounded-[5px] border-[1.5px] border-faint text-transparent transition-colors',
          checked && 'border-primary bg-primary text-primary-foreground',
        )}
      >
        <Check className="size-3" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 text-xs">
          <Mono className="text-muted-foreground">{d.id}</Mono>
          <PriorityDot priority={d.priority} />
        </div>
        <div className="my-0.5 truncate text-[14.5px] font-semibold">{d.title}</div>
        <div className="truncate text-xs text-faint">
          {d.type} · {d.requirement}
        </div>
      </div>
      <div className="flex flex-none items-center gap-2">
        <ListChips lists={lists} defectId={d.id} max={1} />
      </div>
    </div>
  )
})

/** 筛选区:类型、优先级、规划版本、关联需求、只看未入清单。 */
function FilterPanel({
  filter,
  onChange,
  open,
  onToggleOpen,
  defects,
  count,
}: {
  filter: EditorFilter
  onChange: (f: EditorFilter) => void
  open: boolean
  onToggleOpen: () => void
  defects: Defect[]
  count: number
}) {
  const versions = useMemo(() => distinctValues(defects, 'version'), [defects])
  const requirements = useMemo(() => distinctValues(defects, 'requirement'), [defects])

  return (
    <div className="flex flex-none flex-col gap-[11px] border-y bg-panel-2 px-[22px] py-3">
      <div className="flex items-center gap-2.5">
        <b className="text-[13px]">筛选缺陷</b>
        {count > 0 && <Tag tone="accent">{count}</Tag>}
        <span className="flex-1" />
        {count > 0 && (
          <Button size="sm" variant="ghost" onClick={() => onChange(emptyFilter())}>
            清除筛选
          </Button>
        )}
        <Button size="sm" variant="ghost" onClick={onToggleOpen} aria-expanded={open}>
          {open ? '收起' : '展开'}
          {open ? <ChevronUp /> : <ChevronDown />}
        </Button>
      </div>
      {open && (
        <>
          <FilterRow label="类型">
            {DEFECT_TYPES.map((t: DefectType) => (
              <Chip key={t} on={filter.types.has(t)} onClick={() => onChange({ ...filter, types: toggleItem(filter.types, t) })}>
                {t}
              </Chip>
            ))}
          </FilterRow>
          <FilterRow label="优先级">
            {PRIORITIES.map((p: Priority) => (
              <Chip key={p} on={filter.priorities.has(p)} onClick={() => onChange({ ...filter, priorities: toggleItem(filter.priorities, p) })}>
                <i className="size-[7px] rounded-full" style={{ background: PRIORITY_COLOR[p] }} />
                {p}
              </Chip>
            ))}
          </FilterRow>
          <div className="flex items-center gap-2.5">
            <AutoFilter label="版本" placeholder="规划版本,如 3.8" options={versions} value={filter.version} onChange={(version) => onChange({ ...filter, version })} />
            <AutoFilter label="需求" placeholder="关联需求,如 账号" options={requirements} value={filter.requirement} onChange={(requirement) => onChange({ ...filter, requirement })} />
          </div>
          <label className="flex items-center gap-2.5 text-[13px]">
            <Switch label="只看还没加入任何清单的缺陷" checked={filter.unlistedOnly} onCheckedChange={(unlistedOnly) => onChange({ ...filter, unlistedOnly })} />
            只看还没加入任何清单的缺陷
          </label>
        </>
      )}
    </div>
  )
}

function FilterRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="w-12 flex-none text-xs font-semibold text-muted-foreground">{label}</span>
      <div className="flex flex-wrap gap-[7px]">{children}</div>
    </div>
  )
}

function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={cn(
        'inline-flex h-7 items-center gap-1.5 rounded-full border bg-card px-[11px] text-[12.5px] text-muted-foreground transition-colors hover:border-faint',
        on && 'border-primary bg-primary-soft font-medium text-primary-text hover:border-primary',
      )}
    >
      {children}
    </button>
  )
}

/** 带模糊补全的筛选输入。选中后变成可移除的标记。 */
function AutoFilter({
  label,
  placeholder,
  options,
  value,
  onChange,
}: {
  label: string
  placeholder: string
  options: string[]
  value: string
  onChange: (v: string) => void
}) {
  const [query, setQuery] = useState('')
  const [focused, setFocused] = useState(false)

  if (value) {
    return (
      <div className="min-w-0 flex-1">
        <span className="inline-flex h-7 max-w-full items-center gap-1 rounded-full bg-primary-soft pr-1.5 pl-2.5 text-[12.5px] text-primary-text">
          <span className="truncate">
            {label} {value}
          </span>
          <button
            type="button"
            aria-label={`清除${label}筛选`}
            onClick={() => onChange('')}
            className="grid size-[18px] flex-none place-items-center rounded-full opacity-70 hover:bg-primary/20 hover:opacity-100"
          >
            <X className="size-2.5" />
          </button>
        </span>
      </div>
    )
  }

  const q = query.trim()
  const hits = q ? options.filter((o) => fuzzy(q, o)) : []
  return (
    <div className="relative min-w-0 flex-1">
      <Input
        className="h-8 rounded-md bg-card px-2.5 text-[13px] md:text-[13px] dark:bg-card"
        placeholder={placeholder}
        aria-label={`${label}筛选`}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => setFocused(true)}
        onBlur={() => setFocused(false)}
      />
      {focused && q && (
        <div className="absolute top-full right-0 left-0 z-10 mt-1 overflow-hidden rounded-md border bg-popover shadow-pop">
          {hits.length ? (
            hits.map((h) => (
              <button
                key={h}
                type="button"
                // 用 mousedown 选择,避免输入框先失焦把列表收起
                onMouseDown={(e) => {
                  e.preventDefault()
                  onChange(h)
                  setQuery('')
                }}
                className="block w-full px-[11px] py-[7px] text-left text-[13px] hover:bg-primary-soft"
              >
                {h}
              </button>
            ))
          ) : (
            <div className="px-[11px] py-2 text-xs text-faint">没有匹配项</div>
          )}
        </div>
      )}
    </div>
  )
}

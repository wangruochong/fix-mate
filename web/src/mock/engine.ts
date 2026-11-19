import { listHasProgress } from '@/lib/defect'
import { isUndone, type Defect, type Fix, type PauseCause } from '@/types/defect'
import type { AppNotification, NotificationKind, ServerEvent } from '@/types/events'
import type { DefectList, ListState } from '@/types/list'
import { activeList, listState, toApiLists } from './derive'
import { seedDefects, seedLists, type ListRecord } from './seed'

/** AI 每推进一步的间隔。 */
export const STEP_INTERVAL = 1600
/** 复核耗时。 */
const RECHECK_DELAY = 1800

const NEW_POOL: Pick<Defect, 'title' | 'type' | 'priority' | 'requirement' | 'version'>[] = [
  { title: '启动页偶现白屏超过 3 秒', type: 'Bug', priority: 'Critical', requirement: '账号体系改版', version: 'v3.8.0' },
  { title: '订单列表筛选后分页错乱', type: 'Bug', priority: 'Major', requirement: '支付链路优化 · 海外多币种结算与风控联动改造(二期)', version: 'v3.8.0' },
  { title: '希望增加更多主题配色', type: '建议', priority: 'Minor', requirement: '设置页重构', version: 'v3.8.0' },
]

export interface EngineOptions {
  random?: () => number
  now?: () => number
}

/**
 * 浏览器内的模拟后端:保存全部数据,实现清单调度、紧急插队、暂停恢复、接受流程等业务规则。
 * 真实后端用 Python 实现同一份接口,界面不需要改动。
 */
export class Engine {
  defects: Defect[] = []
  lists: ListRecord[] = []
  notifications: AppNotification[] = []
  /** 模拟 main 分支的版本号,每接受一个缺陷加一 */
  mainRev = 0

  private seqN = 3
  private listSeq = 4
  private notifySeq = 0
  private newN = 0
  private lastActiveId: string | null | undefined
  private lastStates = new Map<string, ListState>()
  private accepting = new Set<string>()
  /** 缺陷暂停时 main 的版本,恢复时用来判断是否要同步最新 main(不对外暴露) */
  private pausedAtRev = new Map<string, number>()
  private listeners = new Set<(e: ServerEvent) => void>()
  private timer: ReturnType<typeof setInterval> | undefined
  private random: () => number
  private now: () => number

  constructor(opts: EngineOptions = {}) {
    this.random = opts.random ?? Math.random
    this.now = opts.now ?? Date.now
    this.reset()
  }

  /* ---------- 基础 ---------- */

  reset() {
    this.defects = seedDefects()
    this.lists = seedLists()
    this.notifications = []
    this.mainRev = 0
    this.seqN = 3
    this.listSeq = 4
    this.newN = 0
    this.lastActiveId = undefined
    this.lastStates.clear()
    this.accepting.clear()
    this.tick()
  }

  subscribe(fn: (e: ServerEvent) => void) {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  private emit(e: ServerEvent) {
    for (const fn of [...this.listeners]) fn(e)
  }

  /** 开始定时推进 AI 处理。 */
  start() {
    if (this.timer) return
    this.timer = setInterval(() => this.step(), STEP_INTERVAL)
  }

  stop() {
    clearInterval(this.timer)
    this.timer = undefined
  }

  private iso() {
    return new Date(this.now()).toISOString()
  }

  private byId() {
    return new Map(this.defects.map((d) => [d.id, d]))
  }

  private get(id: string) {
    return this.defects.find((d) => d.id === id)
  }

  private list(id: string) {
    const l = this.lists.find((x) => x.id === id)
    if (!l) throw new Error(`清单不存在:${id}`)
    return l
  }

  private defect(id: string) {
    const d = this.get(id)
    if (!d) throw new Error(`缺陷不存在:${id}`)
    return d
  }

  private listsOf(id: string) {
    return this.lists.filter((l) => l.defectIds.includes(id))
  }

  private urgent() {
    return this.lists.find((l) => l.urgent)!
  }

  private state(l: ListRecord) {
    return listState(l, this.lists, this.byId())
  }

  private active() {
    return activeList(this.lists, this.byId())
  }

  private defectsOf(l: ListRecord) {
    return l.defectIds.map((id) => this.get(id)).filter((d): d is Defect => !!d)
  }

  private notify(title: string, body: string, kind: NotificationKind, defectId?: string, quiet = false) {
    if (!quiet) {
      this.notifications.unshift({
        id: `N-${++this.notifySeq}`,
        title,
        body,
        kind,
        defectId,
        unread: true,
        createdAt: this.iso(),
      })
    }
    this.emit({ type: 'toast', title, body, kind, defectId, quiet })
  }

  private changed() {
    this.emit({ type: 'changed' })
  }

  /* ---------- 查询 ---------- */

  getDefects() {
    return this.defects
  }

  getLists(): DefectList[] {
    return toApiLists(this.lists, this.defects)
  }

  getNotifications() {
    return this.notifications
  }

  markAllRead() {
    this.notifications.forEach((n) => (n.unread = false))
    this.changed()
  }

  /* ---------- 清单 ---------- */

  /** 开始或继续一个清单:排到处理队列队尾,不打断正在处理的清单。 */
  startList(id: string) {
    const l = this.list(id)
    const before = this.state(l)
    if (before === 'running' || before === 'queued') return
    const resumed = listHasProgress(this.defectsOf(l))
    l.on = true
    l.seq = ++this.seqN
    this.tick()
    const after = this.state(l)
    const a = this.active()
    if (after === 'running') this.notify(`${resumed ? '继续' : '开始'}处理「${l.name}」`, 'AI 会按顺序逐个修复', 'new', undefined, true)
    else if (after === 'queued' && a) this.notify(`「${l.name}」已加入处理队列`, `前面还有「${a.name}」,轮到后会自动开始`, 'new', undefined, true)
  }

  pauseList(id: string, silent = false) {
    const l = this.list(id)
    l.on = false
    for (const d of this.defectsOf(l)) if (d.state === 'analyzing') this.pause(d, 'user')
    if (!silent) {
      this.notify(`已暂停「${l.name}」`, '进度已保存,继续时从暂停处接着处理', 'skip', undefined, true)
      this.tick()
    }
  }

  /** 让清单插到队首,正在处理的清单暂时让位。对待处理的清单等于开始并插队。 */
  jumpList(id: string) {
    const l = this.list(id)
    const a = this.active()
    const seqs = this.lists.filter((x) => x.on && !x.urgent).map((x) => x.seq)
    const min = seqs.length ? Math.min(...seqs) : 1
    l.on = true
    l.seq = min - 1
    this.tick()
    this.notify(`已优先处理「${l.name}」`, a && a !== l ? `「${a.name}」暂时让位,进度已保存` : 'AI 会按顺序逐个修复', 'new', undefined, true)
  }

  createList(input: { name: string; defectIds: string[] }) {
    const id = `L-${String(++this.listSeq).padStart(4, '0')}`
    this.lists.push({ id, name: input.name.trim(), createdAt: this.iso(), on: false, seq: 0, defectIds: [...input.defectIds] })
    this.notify(`已创建清单「${input.name.trim()}」`, `${input.defectIds.length} 个缺陷 · 点击卡片即可查看并开始处理`, 'ok', undefined, true)
    this.tick()
    return id
  }

  updateList(id: string, input: { name: string; defectIds: string[] }) {
    const l = this.list(id)
    if (l.urgent) throw new Error('紧急清单不能编辑')
    l.name = input.name.trim()
    l.defectIds = [...input.defectIds]
    this.notify(`已保存「${l.name}」`, `${l.defectIds.length} 个缺陷`, 'ok', undefined, true)
    this.tick()
  }

  deleteList(id: string) {
    const l = this.list(id)
    if (l.urgent) throw new Error('紧急清单不能删除')
    if (this.state(l) === 'running') this.pauseList(id, true)
    this.lists = this.lists.filter((x) => x.id !== id)
    this.notify(`已删除清单「${l.name}」`, '清单里的缺陷仍可以在搜索中找到', 'skip', undefined, true)
    this.tick()
  }

  addToList(listId: string, defectId: string) {
    const l = this.list(listId)
    const d = this.defect(defectId)
    const was = this.state(l)
    const wasUndone = isUndone(d)
    if (!l.defectIds.includes(defectId)) l.defectIds.push(defectId)
    // 处理完成的清单加入新的未处理缺陷后,自动排到队尾
    if (was === 'done' && wasUndone && l.on) l.seq = ++this.seqN
    const now = this.state(l)
    let msg = defectId
    if (was === 'done' && wasUndone) {
      msg =
        now === 'running'
          ? '清单已自动重新开始处理,AI 会处理新加入的缺陷'
          : now === 'queued'
            ? '清单重新进入处理队列,轮到后会自动处理'
            : '清单保持暂停,继续后会处理它'
    } else if (now === 'running') msg = '已排到清单末尾,会按顺序处理'
    this.notify(`已添加到「${l.name}」`, msg, 'ok', undefined, true)
    this.tick()
  }

  removeFromList(listId: string, defectId: string) {
    const l = this.list(listId)
    l.defectIds = l.defectIds.filter((x) => x !== defectId)
    this.notify(`已从「${l.name}」中删除`, defectId, 'skip', undefined, true)
    this.tick()
  }

  /* ---------- 缺陷 ---------- */

  private pause(d: Defect, cause: PauseCause, note?: string) {
    d.state = 'paused'
    this.pausedAtRev.set(d.id, this.mainRev)
    d.pause = {
      cause,
      at: this.iso(),
      note,
      confidence: (d.step ?? 0) >= 1 ? 86 + Math.floor(this.random() * 10) : undefined,
    }
  }

  pauseDefect(id: string) {
    const d = this.defect(id)
    const running = this.listsOf(id).find((l) => this.state(l) === 'running')
    if (running) {
      this.pauseList(running.id)
    } else {
      this.pause(d, 'user')
      this.changed()
    }
  }

  resumeDefect(id: string) {
    const ls = this.listsOf(id)
    const l =
      ls.find((x) => this.state(x) === 'pending') ??
      ls.find((x) => ['running', 'queued'].includes(this.state(x))) ??
      ls[0]
    if (l) this.startList(l.id)
  }

  /** 立即处理:加入紧急清单。front 会打断当前的紧急缺陷,back 排在紧急队列后面。 */
  addUrgent(id: string, position: 'front' | 'back') {
    const u = this.urgent()
    if (position === 'front') u.defectIds = [id, ...u.defectIds.filter((x) => x !== id)]
    else if (!u.defectIds.includes(id)) u.defectIds.push(id)
    u.on = true
    if (position === 'front') {
      for (const x of this.defects) {
        if (x.state === 'analyzing' && x.id !== id && u.defectIds.includes(x.id)) this.pause(x, 'preempted')
      }
    }
    this.notify('已加入紧急处理', `${id} ${position === 'front' ? '马上开始处理' : '会在紧急队列中依次处理'}`, 'warn', undefined, true)
    this.tick()
  }

  reject(id: string, input: { keepChanges: boolean; reason?: string }) {
    const d = this.defect(id)
    d.state = 'rejected'
    d.outcome = { kind: 'rejected', keepChanges: input.keepChanges, reason: input.reason?.trim() || undefined }
    this.notify(`已拒绝 ${id}`, input.keepChanges ? 'AI 修改已保留到工作区' : 'AI 修改已丢弃', 'skip')
    this.tick()
  }

  pass(id: string, reason: string) {
    const d = this.defect(id)
    d.state = 'passed'
    d.outcome = { kind: 'passed', auto: false, reason: reason.trim() }
    this.notify(`已跳过 ${id}`, reason.trim(), 'skip')
    this.tick()
  }

  /** 接受流程共 7 步,通过 accept-progress 事件逐步汇报,最后一步完成后缺陷变为已接受。 */
  accept(id: string) {
    const d = this.defect(id)
    if (d.state !== 'review' || !d.fix || this.accepting.has(id)) return
    this.accepting.add(id)
    const ota = `3.8.0.${2400 + Math.floor(this.random() * 90)}`
    let n = 0
    this.emit({ type: 'accept-progress', defectId: id, step: 0 })
    const next = () => {
      n++
      if (n === 7) {
        d.state = 'accepted'
        d.needsRecheck = undefined
        d.outcome = { kind: 'accepted', ota, commit: d.fix!.commit }
        this.mainRev++
        this.accepting.delete(id)
        this.emit({ type: 'accept-progress', defectId: id, step: 7, ota })
        this.notify(`已接受 ${id}`, `OTA ${ota} 已打包,飞书已评论 #${ota}`, 'ok', id)
        this.tick()
      } else {
        this.emit({ type: 'accept-progress', defectId: id, step: n, ota: n > 4 ? ota : undefined })
        setTimeout(next, n === 4 ? 1800 : 650)
      }
    }
    setTimeout(next, 650)
  }

  recheck(id: string) {
    const d = this.defect(id)
    if (d.state !== 'review' || !d.fix || d.rechecking) return
    d.rechecking = true
    this.changed()
    setTimeout(() => {
      d.rechecking = false
      d.needsRecheck = false
      d.fix!.recheck = '已结合最新 main(含已合入的相关修改)与缓存结论重新评估:原方案调整为复用已有的校验函数,冲突已消除。'
      d.fix!.conflicts = []
      d.fix!.commit = this.hex(7)
      this.notify('复核完成', `${id} 的方案已基于最新代码更新`, 'ok', id)
      this.changed()
    }, RECHECK_DELAY)
  }

  /** 模拟从飞书收到一个新缺陷,默认不在任何清单里。 */
  simulateNewDefect() {
    const t = NEW_POOL[this.newN++ % NEW_POOL.length]
    const d: Defect = {
      ...t,
      id: `${t.type === '建议' ? 'SUG' : 'BUG'}-${2490 + this.newN}`,
      reporter: '飞书同学',
      createdAt: this.iso(),
      description: `(模拟的新缺陷)${t.title}。`,
      state: 'queued',
    }
    this.defects.unshift(d)
    this.notify('收到新缺陷 · 尚未加入清单', `${d.id} · ${d.priority} · ${d.title}`, 'warn', d.id)
    this.changed()
    return d
  }

  /** 批量加入缺陷,用于压力测试。 */
  addDefects(list: Defect[]) {
    this.defects.unshift(...list)
    this.changed()
  }

  /* ---------- 调度 ---------- */

  /** AI 推进一步:每个处理中的缺陷前进一个步骤,走完后进入待审核。 */
  step() {
    let changed = false
    for (const d of this.defects.filter((x) => x.state === 'analyzing')) {
      d.step = (d.step ?? 0) + 1
      changed = true
      if (d.type === '建议' && d.step >= 1) {
        d.state = 'passed'
        d.outcome = {
          kind: 'passed',
          auto: true,
          reason: 'AI 判断:这是一条产品体验类建议,没有确定的代码修改目标,已自动跳过。如需处理请手动调整。',
        }
        this.notify(`AI 已跳过 ${d.id}`, '不是可通过改代码解决的确定问题', 'skip', d.id)
      } else if (d.step >= 3) {
        d.state = 'review'
        d.rebased = undefined
        d.needsRecheck = this.listsOf(d.id).some((l) => l.defectIds.some((x) => x !== d.id && this.get(x)?.state === 'review'))
        d.fix ??= this.generateFix(d)
        if (d.needsRecheck) d.cached = { at: this.iso(), baseCommit: 'a3f9c21', text: d.fix.conclusion.map((s) => (typeof s === 'string' ? s : 'code' in s ? s.code : s.bold)).join('') }
        this.notify(`方案已就绪 · ${d.id}`, d.title, 'new', d.id)
      }
    }
    if (changed) this.tick()
  }

  /**
   * 核心调度:把不在活跃清单里的处理中缺陷暂停,再从活跃清单里取第一个未处理完的缺陷开始处理。
   * 每次状态可能变化后都要调用。
   */
  tick() {
    const a = this.active()
    for (const d of this.defects) {
      if (d.state === 'analyzing' && !(a && a.defectIds.includes(d.id))) {
        this.pause(d, this.listsOf(d.id).some((l) => l.on) ? 'preempted' : 'user')
      }
    }
    if (a) {
      const ds = this.defectsOf(a)
      if (!ds.some((d) => d.state === 'analyzing')) {
        const next = ds.find((d) => d.state === 'queued' || d.state === 'paused')
        if (next) {
          if (next.state === 'queued') next.step = 0
          else if (next.pause?.cause === 'preempted' && this.mainRev > (this.pausedAtRev.get(next.id) ?? 0)) next.rebased = true
          next.pause = undefined
          next.state = 'analyzing'
        }
      }
    }
    const activeId = a?.id ?? null
    if (activeId !== this.lastActiveId) {
      if (this.lastActiveId !== undefined) {
        const last = this.lists.find((l) => l.id === this.lastActiveId)
        if (a?.urgent) this.notify('紧急处理中', 'AI 已切换去处理紧急缺陷,其它清单暂时让位,进度已保存', 'warn')
        else if (last?.urgent && a) this.notify(`已自动恢复「${a.name}」`, '紧急缺陷处理完成,从上次暂停处继续', 'ok', undefined, true)
      }
      this.lastActiveId = activeId
    }
    for (const l of this.lists) {
      const s = this.state(l)
      const prev = this.lastStates.get(l.id)
      if (prev !== undefined && prev !== s && s === 'done' && prev !== 'pending') {
        const n = this.defectsOf(l).filter((d) => d.state === 'review').length
        this.notify(l.urgent ? '紧急缺陷已处理完' : `「${l.name}」处理完成`, n ? `还有 ${n} 个缺陷等你审核` : '都已处理完毕', 'done')
      }
      this.lastStates.set(l.id, s)
    }
    this.changed()
  }

  /* ---------- 生成假方案 ---------- */

  hex(n: number) {
    return Array.from({ length: n }, () => Math.floor(this.random() * 16).toString(16)).join('')
  }

  private generateFix(d: Defect): Fix {
    const module = d.requirement.replace(/\s/g, '').slice(0, 8)
    return {
      confidence: 85 + Math.floor(this.random() * 10),
      branch: `fixmate/${d.id}`,
      commit: this.hex(7),
      judge: '问题描述明确,可通过修改代码解决。',
      summary: [['定位到相关模块并修复'], ['补充必要的测试']],
      conclusion: ['已分析根因并完成修复,详见 diff。'],
      files: [
        {
          name: `src/modules/${module}/index.ts`,
          additions: 8,
          deletions: 3,
          lines: [
            { kind: 'hunk', text: '@@ -20,6 +20,11 @@' },
            { kind: 'del', text: '-   return legacy(x)' },
            { kind: 'add', text: '+   return safe(x)' },
          ],
        },
      ],
      conflicts: [],
    }
  }
}

export const engine = new Engine()

/** 缺陷状态,共七种,见设计文档第 5 节。 */
export type DefectState =
  | 'queued' // 排队中
  | 'analyzing' // AI 处理中
  | 'paused' // 已暂停
  | 'review' // 待审核
  | 'accepted' // 已接受(终态)
  | 'rejected' // 已拒绝(终态)
  | 'passed' // 已跳过(终态)

export type DefectType = 'Bug' | '建议' | '测试需求' | '历史遗留问题'

export type Priority = 'Blocker' | 'Critical' | 'Major' | 'Minor'

/** 行内富文本片段,替代原型里直接写进数据的 HTML。 */
export type RichSegment = string | { code: string } | { bold: string }
export type RichText = RichSegment[]

export type DiffLineKind = 'hunk' | 'ctx' | 'add' | 'del'

export interface DiffLine {
  kind: DiffLineKind
  text: string
}

export interface FixFile {
  name: string
  additions: number
  deletions: number
  lines: DiffLine[]
}

/** 与另一个缺陷修改了同一文件。 */
export interface FixConflict {
  with: string
  file: string
  range: string
}

/** AI 生成的修复方案。 */
export interface Fix {
  confidence: number
  branch: string
  commit: string
  judge: string
  summary: RichText[]
  conclusion: RichText
  files: FixFile[]
  conflicts: FixConflict[]
  /** 复核后写入的结果说明 */
  recheck?: string
}

/** 修复时缓存的结论摘要,复核时使用。 */
export interface CachedConclusion {
  at: string
  baseCommit: string
  text: string
}

/** 暂停原因:用户手动暂停需要手动继续,被插队打断会自动恢复。 */
export type PauseCause = 'user' | 'preempted'

export interface PauseInfo {
  cause: PauseCause
  at: string
  /** 已有的中间结果 */
  note?: string
  /** 暂停前 AI 判断出的置信度(已完成判断时才有) */
  confidence?: number
  /** 被打断时的 main 版本,恢复时用来判断是否要同步 */
  mainRev?: number
}

export type Outcome =
  | { kind: 'accepted'; ota: string; commit: string }
  | { kind: 'rejected'; keepChanges: boolean; reason?: string }
  | { kind: 'passed'; auto: boolean; reason: string }

export interface Defect {
  id: string
  title: string
  type: DefectType
  priority: Priority
  requirement: string
  version: string
  reporter: string
  createdAt: string
  description: string
  state: DefectState
  /** analyzing / paused 时所处的步骤,从 0 开始 */
  step?: number
  pause?: PauseInfo
  /** 被插队打断后恢复时,已把临时分支同步到最新 main */
  rebased?: boolean
  /** 正在复核 */
  rechecking?: boolean
  fix?: Fix
  /** 待审核时,是否需要复核 */
  needsRecheck?: boolean
  cached?: CachedConclusion
  /** accepted / rejected / passed 时的处理结果 */
  outcome?: Outcome
}

/** AI 视角下「未处理完」的状态。 */
export const UNDONE_STATES: readonly DefectState[] = ['queued', 'analyzing', 'paused']

export const isUndone = (d: Pick<Defect, 'state'>) => UNDONE_STATES.includes(d.state)

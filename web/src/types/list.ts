/** 清单状态,共四种,见设计文档第 4 节。 */
export type ListState =
  | 'pending' // 待处理:没开始过,或被用户暂停,且还有未处理完的缺陷
  | 'queued' // 排队中:用户已点过,前面还有别的清单
  | 'running' // 处理中
  | 'done' // 处理完成:没有未处理完的缺陷

export interface DefectList {
  id: string
  name: string
  /** 内置的紧急清单,置顶,不能编辑和删除 */
  urgent?: boolean
  createdAt: string
  /** 缺陷在清单中的顺序 */
  defectIds: string[]
  /** 由缺陷状态推导,不单独存储 */
  state: ListState
}

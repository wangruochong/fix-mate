import type { RichText } from '@/types/defect'

/** 接受后系统自动完成的 7 个步骤,与设计文档第 6 节一致。 */
export const acceptSteps = (branch: string): RichText[] => [
  ['切换到主分支 ', { code: 'main' }],
  ['cherry-pick ', { code: branch }, ' 上的提交'],
  ['删除本地临时分支'],
  ['push 到 ', { code: 'origin/main' }],
  ['调用 Jenkins 打 OTA 包'],
  ['在飞书将缺陷标记为「已解决」'],
  ['在飞书评论中备注版本号 ', { code: '#{ota_version}' }],
]

/** 进行到第 step 步时,第 index 步显示的文字:第 5、7 步完成后带上 OTA 版本号。 */
export function acceptStepText(branch: string, index: number, step: number, ota?: string): RichText {
  if (index === 4) return step > 4 && ota ? ['OTA 已完成,版本号 ', { code: ota }] : ['Jenkins 打 OTA 包(预计约 1 分钟)']
  if (index === 6 && step > 6 && ota) return ['已评论 ', { code: `#${ota}` }]
  return acceptSteps(branch)[index]
}

/** 接受流程每一步的名字,用在失败提示里,与后端 `ACCEPT_STEPS` 一致。 */
export const ACCEPT_STEP_NAMES = [
  '切换到主分支',
  '把修复放进主分支',
  '删除临时分支',
  '推送到远端',
  '打 OTA 包',
  '在飞书标记为已解决',
  '在飞书评论版本号',
] as const

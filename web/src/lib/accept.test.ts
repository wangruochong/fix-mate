import { describe, expect, it } from 'vitest'
import { acceptStepText, acceptSteps } from './accept'

describe('接受流程文案', () => {
  it('共 7 步', () => expect(acceptSteps('fixmate/BUG-1')).toHaveLength(7))
  it('第 5 步完成前不显示版本号', () => {
    expect(acceptStepText('b', 4, 4, '3.8.0.2417')).toEqual(['Jenkins 打 OTA 包(预计约 1 分钟)'])
  })
  it('第 5 步完成后显示 OTA 版本号', () => {
    expect(acceptStepText('b', 4, 5, '3.8.0.2417')).toEqual(['OTA 已完成,版本号 ', { code: '3.8.0.2417' }])
  })
  it('第 7 步完成后显示评论内容', () => {
    expect(acceptStepText('b', 6, 7, '3.8.0.2417')).toEqual(['已评论 ', { code: '#3.8.0.2417' }])
  })
  it('其它步骤沿用原文案', () => {
    expect(acceptStepText('fixmate/BUG-1', 1, 0)).toEqual(['cherry-pick ', { code: 'fixmate/BUG-1' }, ' 上的提交'])
  })
})

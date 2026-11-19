import { fakerZH_CN as faker } from '@faker-js/faker'
import { DEFECT_TYPES, PRIORITIES } from '@/lib/defect'
import type { Defect, DefectState } from '@/types/defect'

const REQUIREMENTS = ['账号体系改版', '个人中心 2.0', '报表中心', '消息中心重构', '设置页重构', '支付链路优化']
const VERSIONS = ['v3.8.0', 'v3.7.2', 'v3.7.1', 'v3.6.5']
const SUBJECTS = ['登录页', '订单列表', '个人中心', '报表导出', '消息推送', '设置页', '支付回调', '搜索结果', '启动页', '头像上传']
const PROBLEMS = ['偶现白屏', '点击无响应', '显示错位', '提示信息不准确', '加载很慢', '数据不同步', '闪退', '文案有误', '动画卡顿']

/** 状态占比:大部分在排队,少量已处理,贴近真实使用时的分布。 */
const STATE_WEIGHTS: [DefectState, number][] = [
  ['queued', 70],
  ['accepted', 12],
  ['rejected', 6],
  ['passed', 8],
  ['paused', 4],
]

function pickState(): DefectState {
  const total = STATE_WEIGHTS.reduce((a, [, w]) => a + w, 0)
  let r = faker.number.int({ min: 1, max: total })
  for (const [state, w] of STATE_WEIGHTS) {
    if ((r -= w) <= 0) return state
  }
  return 'queued'
}

/** 生成 n 条随机缺陷,id 从 startId 开始递增。 */
export function fakeDefects(n: number, startId = 5000): Defect[] {
  return Array.from({ length: n }, (_, i) => {
    const type = faker.helpers.arrayElement(DEFECT_TYPES)
    const state = pickState()
    const id = `${type === '建议' ? 'SUG' : 'BUG'}-${startId + i}`
    const d: Defect = {
      id,
      title: `${faker.helpers.arrayElement(SUBJECTS)}${faker.helpers.arrayElement(PROBLEMS)}`,
      type,
      priority: faker.helpers.arrayElement(PRIORITIES),
      requirement: faker.helpers.arrayElement(REQUIREMENTS),
      version: faker.helpers.arrayElement(VERSIONS),
      reporter: faker.person.lastName() + faker.person.firstName(),
      createdAt: faker.date.recent({ days: 30 }).toISOString(),
      description: faker.lorem.sentence(),
      state,
    }
    if (state === 'accepted') d.outcome = { kind: 'accepted', ota: `3.7.2.${faker.number.int({ min: 2000, max: 2399 })}`, commit: faker.git.commitSha({ length: 7 }) }
    if (state === 'rejected') d.outcome = { kind: 'rejected', keepChanges: faker.datatype.boolean() }
    if (state === 'passed') d.outcome = { kind: 'passed', auto: false, reason: '需求描述不明确,需先和产品确认。' }
    if (state === 'paused') {
      d.step = 2
      d.pause = { cause: 'user', at: new Date().toISOString() }
    }
    return d
  })
}

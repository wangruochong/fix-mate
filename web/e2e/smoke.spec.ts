import { expect, test, type Page } from '@playwright/test'

/** 每个用例开始时都重置假数据,并收集控制台报错。 */
let errors: string[]

test.beforeEach(async ({ page }) => {
  errors = []
  page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', (e) => errors.push(String(e)))
  await page.goto('/')
  await page.getByText('本周迭代').first().waitFor()
  await page.getByRole('button', { name: '重置数据' }).click()
  await page.waitForTimeout(300)
})

test.afterEach(() => {
  expect(errors, '页面不应有控制台报错').toEqual([])
})

const nav = (page: Page, name: string) => page.locator('nav').getByRole('button', { name }).first()
const row = (page: Page, title: string) => page.getByRole('button').filter({ hasText: title }).first()

test('三个主页面可以切换,清单卡片点击跳到缺陷页', async ({ page }) => {
  await nav(page, '清单').click()
  await expect(page.getByText('把要处理的缺陷分组')).toBeVisible()
  await expect(page.getByText('有 3 个缺陷还没加入任何清单')).toBeVisible()
  await page.getByText('账号体系改版', { exact: true }).first().click()
  await expect(page.getByText('已暂停于 TST-0933')).toBeVisible()
  await nav(page, '搜索').click()
  await expect(page.getByText('搜索任意缺陷')).toBeVisible()
})

test('搜索支持模糊匹配和无结果', async ({ page }) => {
  await nav(page, '搜索').click()
  await page.getByPlaceholder(/关键词/).fill('登录')
  await page.keyboard.press('Enter')
  await expect(page.getByText('找到 3 个匹配「登录」的缺陷')).toBeVisible()
  await page.getByPlaceholder(/关键词/).fill('zzzz')
  await page.keyboard.press('Enter')
  await expect(page.getByText('没有找到相关缺陷')).toBeVisible()
})

test('暂停和继续清单', async ({ page }) => {
  await expect(page.getByText('处理中').first()).toBeVisible()
  await page.getByRole('button', { name: '暂停处理' }).click()
  await expect(page.getByText(/已暂停于 [A-Z]+-\d+/)).toBeVisible()
  await page.getByRole('button', { name: '继续处理' }).first().click()
  await expect(page.getByText('已暂停于')).toHaveCount(0)
})

test('AI 会自己推进:处理中的缺陷走完后进入待审核', async ({ page }) => {
  await expect(row(page, '弱网下订单提交可能重复扣款')).toContainText('AI 处理中')
  await expect(row(page, '弱网下订单提交可能重复扣款')).toContainText('待审核', { timeout: 10_000 })
  await expect(row(page, '个人中心头像裁剪后显示被拉伸')).toContainText('AI 处理中')
})

test('接受流程:7 步完成后缺陷变为已接受', async ({ page }) => {
  await row(page, '登录页点击「忘记密码」无响应').click()
  await page.getByRole('button', { name: '接受并发布' }).click()
  await page.getByRole('button', { name: '确认接受' }).click()
  await expect(page.getByRole('heading', { name: '已接受并发布' })).toBeVisible({ timeout: 15_000 })
  await page.getByRole('button', { name: '完成' }).click()
  await expect(page.getByText(/commit e4b7a90/)).toBeVisible()
})

test('待复核的缺陷必须先复核才能接受', async ({ page }) => {
  await row(page, '登录失败时提示信息不准确').click()
  await expect(page.getByRole('button', { name: '接受并发布' })).toBeDisabled()
  await page.getByRole('button', { name: '立即复核' }).click()
  await expect(page.getByText('复核结果')).toBeVisible({ timeout: 5000 })
  await expect(page.getByRole('button', { name: '接受并发布' })).toBeEnabled()
})

test('拒绝和跳过都会记录原因', async ({ page }) => {
  await row(page, '登录页点击「忘记密码」无响应').click()
  await page.getByRole('button', { name: '拒绝', exact: true }).click()
  await page.getByPlaceholder('例如:思路对,但改动范围偏大').fill('范围偏大')
  await page.getByRole('button', { name: '确认拒绝' }).click()
  await expect(page.getByText('已拒绝该方案')).toBeVisible()
  await expect(page.getByText('范围偏大').first()).toBeVisible()
})

test('紧急插队:打断当前缺陷,顶部出现紧急提示条', async ({ page }) => {
  await nav(page, '搜索').click()
  await page.getByPlaceholder(/关键词/).fill('夜间模式')
  await page.keyboard.press('Enter')
  await page.getByRole('button', { name: '立即处理', exact: true }).click()
  await expect(page.getByText('紧急处理中')).toBeVisible()
  await expect(page.getByText('其它清单已暂时让位')).toBeVisible()
  await nav(page, '缺陷').click()
  await expect(row(page, '弱网下订单提交可能重复扣款')).toContainText('紧急插队,已暂停')
})

test('新建、编辑、删除清单', async ({ page }) => {
  await nav(page, '清单').click()
  await page.getByRole('button', { name: '新建清单' }).first().click()
  // 名称必填
  await page.getByText('设置页开关切换动画卡顿').click()
  await page.getByRole('button', { name: /保存清单 · 1 条/ }).click()
  await expect(page.getByText('请先给清单起个名字')).toBeVisible()
  await page.getByPlaceholder('例如:本周必修、登录相关').fill('测试清单')
  await page.getByRole('button', { name: /保存清单 · 1 条/ }).click()
  await expect(page.getByText('测试清单', { exact: true }).first()).toBeVisible()
  await page.getByRole('button', { name: '删除清单' }).last().click()
  await page.getByRole('button', { name: '确认删除' }).click()
  await expect(page.getByText('测试清单', { exact: true })).toHaveCount(0)
})

test('一键新建清单会预选所有未入清单的缺陷', async ({ page }) => {
  await nav(page, '清单').click()
  await page.getByRole('button', { name: '一键新建清单' }).click()
  await expect(page.getByRole('button', { name: /保存清单 · 3 条/ })).toBeVisible()
})

test('模拟新缺陷:出现通知红点和提示', async ({ page }) => {
  await page.getByRole('button', { name: '＋ 模拟新缺陷' }).click()
  await expect(page.getByText('收到新缺陷 · 尚未加入清单').first()).toBeVisible()
  await nav(page, '通知').click()
  await expect(page.getByText('收到新缺陷 · 尚未加入清单').last()).toBeVisible()
})

test('300 条缺陷:搜索和编辑清单仍然流畅', async ({ page }) => {
  await page.getByRole('button', { name: '批量生成 300 条' }).click()
  await page.waitForTimeout(500)
  await nav(page, '清单').click()
  await page.getByRole('button', { name: '新建清单' }).first().click()
  const start = Date.now()
  await page.getByRole('button', { name: '全选' }).click()
  await expect(page.getByRole('button', { name: /保存清单 · 31\d 条/ })).toBeVisible()
  expect(Date.now() - start, '全选 300+ 条应在 2 秒内完成').toBeLessThan(2000)
})

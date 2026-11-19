import { expect, test } from '@playwright/test'

/**
 * 接受流程失败后的体验(只在真实后端下有意义):
 * 缺陷保持待审核,界面说清楚卡在哪一步;打 OTA 包这类不能重做的步骤,第一次重试会被拦下,用户再点一次才继续。
 */
test.beforeEach(async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: '重置数据' }).waitFor()
  await page.evaluate(() => fetch('/api/dev/reset', { method: 'POST' }))
  await page.reload()
  await page.getByText('本周迭代').first().waitFor()
})

test.afterEach(async ({ page }) => {
  await page.evaluate(() => fetch('/api/dev/accept-failure', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }))
})

const fail = (page: import('@playwright/test').Page, step: number | null) =>
  page.evaluate(
    (s) => fetch('/api/dev/accept-failure', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ step: s }) }),
    step,
  )

test('打 OTA 包失败后说明卡在第 5 步,重试被拦下一次,确认后成功', async ({ page }) => {
  await fail(page, 4)
  // 接受 AI 刚修好的缺陷(演示数据里的待审核缺陷带的是编造的提交号,真实引擎无法接受它们)
  const target = page.getByRole('button').filter({ hasText: '弱网下订单提交可能重复扣款' }).first()
  await expect(target).toContainText('待审核', { timeout: 20_000 })
  await target.click()
  await page.getByRole('button', { name: '立即复核' }).click() // 同清单里还有别的待审核方案,需要先复核
  await expect(page.getByText('复核结果')).toBeVisible({ timeout: 10_000 })
  await page.getByRole('button', { name: '接受并发布' }).click()
  await page.getByRole('button', { name: '确认接受' }).click()

  // 失败:弹窗说清楚卡在哪一步
  const failed = page.getByRole('dialog', { name: /卡在了第 5 步/ })
  await expect(failed).toBeVisible({ timeout: 15_000 })
  await expect(failed.getByText('已完成的步骤不会重做')).toBeVisible()
  await failed.getByRole('button', { name: '关闭' }).click()

  // 缺陷仍是待审核,详情里有失败卡片,按钮变成「重试接受」
  await expect(page.getByText('接受卡在了第 5 步「打 OTA 包」')).toBeVisible()
  await fail(page, null) // 故障排除
  await page.getByRole('button', { name: '重试接受' }).click()
  await page.getByRole('button', { name: '确认接受' }).click()

  // 打包可能已经触发过,第一次重试被拦下,要用户先去确认
  const blocked = page.getByRole('dialog', { name: /卡在了第 5 步/ })
  await expect(blocked.getByText(/请先到 Jenkins 确认/)).toBeVisible({ timeout: 15_000 })
  await blocked.getByRole('button', { name: '重试接受' }).click() // 用户确认后再点

  await expect(page.getByRole('heading', { name: '已接受并发布' })).toBeVisible({ timeout: 15_000 })
})

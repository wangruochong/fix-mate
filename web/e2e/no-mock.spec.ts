import { expect, test } from '@playwright/test'

// 关闭假接口后,界面应该报告连接失败,证明没有偷偷依赖假数据。
test.use({ baseURL: 'http://localhost:5198' })

test('关闭假接口后显示连接失败', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByText('连接不上服务')).toBeVisible()
  await expect(page.getByText('本周迭代')).toHaveCount(0)
})

import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  workers: 1,
  use: { baseURL: 'http://localhost:5199', viewport: { width: 1440, height: 900 } },
  webServer: [
    { command: 'npm run dev -- --port 5199 --strictPort', url: 'http://localhost:5199', reuseExistingServer: true },
    // 关闭假接口的实例,用来验证界面没有偷偷依赖假数据
    {
      command: 'npm run dev -- --port 5198 --strictPort',
      url: 'http://localhost:5198',
      reuseExistingServer: true,
      env: { VITE_USE_MOCK: 'false' },
    },
  ],
})

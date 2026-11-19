import { defineConfig } from '@playwright/test'

const BACKEND_PORT = 8123

/**
 * 同一套端到端测试跑两遍:
 * - mock:前端 + 浏览器内的假接口
 * - backend:前端 + 真实的 Python 后端(开发模式:真实的 AI 引擎和 git 沙盒仓库,只有改代码是假的),验证前后端接口契约
 * 另有一个指向不存在的后端的实例,用来确认关闭假接口后界面没有偷偷依赖假数据。
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  workers: 1,
  use: { viewport: { width: 1440, height: 900 } },
  projects: [
    { name: 'mock', testMatch: 'smoke.spec.ts', use: { baseURL: 'http://localhost:5199' } },
    { name: 'backend', testMatch: ['smoke.spec.ts', 'accept-failure.spec.ts'], use: { baseURL: 'http://localhost:5197' } },
    { name: 'no-backend', testMatch: 'no-mock.spec.ts', use: { baseURL: 'http://localhost:5198' } },
  ],
  webServer: [
    { command: 'npm run dev -- --port 5199 --strictPort', url: 'http://localhost:5199', reuseExistingServer: true },
    {
      command: 'npm run dev -- --port 5198 --strictPort',
      url: 'http://localhost:5198',
      reuseExistingServer: true,
      env: { VITE_USE_MOCK: 'false', VITE_BACKEND_URL: 'http://127.0.0.1:9' },
    },
    {
      command: 'npm run dev -- --port 5197 --strictPort',
      url: 'http://localhost:5197',
      reuseExistingServer: true,
      env: { VITE_USE_MOCK: 'false', VITE_BACKEND_URL: `http://127.0.0.1:${BACKEND_PORT}` },
    },
    {
      // 每次启动用全新的临时数据目录,保证从演示数据开始
      command: 'cd ../backend && FIXMATE_DATA_DIR=$(mktemp -d) uv run fix-mate',
      url: `http://127.0.0.1:${BACKEND_PORT}/api/lists`,
      // 后端带着状态,不复用上次遗留的进程,否则可能连到旧代码
      reuseExistingServer: false,
      env: { FIXMATE_ENV: 'dev', FIXMATE_ENGINE: 'graph', FIXMATE_PORT: String(BACKEND_PORT) },
    },
  ],
})

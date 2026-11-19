import { setupWorker } from 'msw/browser'
import { engine } from './engine'
import { handlers } from './handlers'

export const worker = setupWorker(...handlers)

/** 启动假接口和模拟引擎。 */
export async function startMocking() {
  await worker.start({ onUnhandledRequest: 'bypass' })
  engine.start()
}

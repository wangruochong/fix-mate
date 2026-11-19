import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { connectEvents } from './api/events'
import { queryClient } from './api/queryClient'
import { USE_MOCK } from './config'

/** 界面主题跟随系统的深浅色设置。 */
function followSystemTheme() {
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const apply = () => document.documentElement.classList.toggle('dark', media.matches)
  apply()
  media.addEventListener('change', apply)
}

async function bootstrap() {
  followSystemTheme()
  // import.meta.env.DEV 写在这里,正式构建时整段连同假数据一起被去掉
  if (import.meta.env.DEV && USE_MOCK) {
    const { startMocking } = await import('./mock/browser')
    await startMocking()
  }
  connectEvents()
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <App />
      </QueryClientProvider>
    </StrictMode>,
  )
}

void bootstrap()

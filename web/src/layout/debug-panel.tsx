import { actions } from '@/api/actions'
import { useUi } from '@/store/ui'

/** 开发调试面板,只在使用假接口时显示,正式版不会出现。 */
export function DebugPanel() {
  const go = useUi((s) => s.go)
  const btn = 'h-7 rounded-md px-3 text-[12.5px] text-[#c9ced8] hover:bg-white/10 hover:text-white'
  return (
    <div className="fixed bottom-3 left-[calc(var(--rail-w)+14px)] z-60 flex gap-0.5 rounded-lg bg-[rgb(23_26_33/0.88)] p-1 opacity-60 shadow-[0_6px_24px_rgb(0_0_0/0.25)] backdrop-blur-md transition-opacity hover:opacity-100">
      <button type="button" className={btn} onClick={() => go('onboard')}>
        首次启动
      </button>
      <button type="button" className={btn} onClick={() => void actions.dev.newDefect()}>
        ＋ 模拟新缺陷
      </button>
      <button type="button" className={btn} onClick={() => void actions.dev.bulk(300)}>
        批量生成 300 条
      </button>
      <button type="button" className={btn} onClick={() => void actions.dev.reset()}>
        重置数据
      </button>
    </div>
  )
}

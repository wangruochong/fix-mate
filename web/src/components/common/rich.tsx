import type { RichText } from '@/types/defect'
import { Mono } from './feedback'

/** 渲染结构化的行内富文本(代码、加粗),不使用 HTML。 */
export function Rich({ text }: { text: RichText }) {
  return (
    <>
      {text.map((seg, i) =>
        typeof seg === 'string' ? (
          <span key={i}>{seg}</span>
        ) : 'code' in seg ? (
          <Mono key={i}>{seg.code}</Mono>
        ) : (
          <b key={i} className="text-foreground">
            {seg.bold}
          </b>
        ),
      )}
    </>
  )
}

import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog'

/**
 * 弹窗外壳:标题 + 副标题 + 主体 + 右对齐的按钮区。
 * 不使用 shadcn 默认的灰底页脚,与设计稿保持一致。
 */
export function DialogShell({
  open,
  onClose,
  title,
  desc,
  footer,
  children,
}: {
  open: boolean
  onClose: () => void
  title: React.ReactNode
  desc?: React.ReactNode
  footer: React.ReactNode
  children?: React.ReactNode
}) {
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent showCloseButton={false} className="gap-0 rounded-xl p-6 shadow-pop sm:max-w-[520px]">
        <DialogTitle className="mb-1 text-[17px] leading-snug font-semibold">{title}</DialogTitle>
        <DialogDescription className="mb-4 text-[13px]">{desc}</DialogDescription>
        {children}
        <div className="mt-5 flex justify-end gap-2.5">{footer}</div>
      </DialogContent>
    </Dialog>
  )
}

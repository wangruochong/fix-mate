import { Dialog as DrawerPrimitive } from '@base-ui/react/dialog'
import { cn } from 'cn'

/**
 * 右侧半屏侧栏。宽度取 --drawer-w(半屏,最窄 560px)。
 * 点击遮罩或按 Esc 会调用 onClose。内容由调用方决定,通常是固定头部 + 可滚动主体 + 固定底部。
 */
export function Drawer({
  open,
  onClose,
  children,
  className,
}: {
  open: boolean
  onClose: () => void
  children: React.ReactNode
  className?: string
}) {
  return (
    <DrawerPrimitive.Root open={open} onOpenChange={(o) => !o && onClose()}>
      <DrawerPrimitive.Portal>
        <DrawerPrimitive.Backdrop className="fixed inset-0 z-20 bg-[rgb(15_17_24/0.16)] transition-opacity duration-200 data-ending-style:opacity-0 data-starting-style:opacity-0" />
        <DrawerPrimitive.Popup
          className={cn(
            'fixed inset-y-0 right-0 z-21 flex w-(--drawer-w) flex-col border-l bg-card shadow-[-14px_0_44px_rgb(16_24_40/0.16)] outline-none',
            'transition-[transform,opacity] duration-250 ease-[cubic-bezier(.2,.8,.2,1)] data-ending-style:translate-x-12 data-ending-style:opacity-0 data-starting-style:translate-x-12 data-starting-style:opacity-0',
            className,
          )}
        >
          {children}
        </DrawerPrimitive.Popup>
      </DrawerPrimitive.Portal>
    </DrawerPrimitive.Root>
  )
}

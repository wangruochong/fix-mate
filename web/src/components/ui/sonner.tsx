"use client"

import { Toaster as Sonner, type ToasterProps } from "sonner"

/** 提示框的外观由 lib/toast.tsx 里的自定义内容决定,这里只负责位置。主题跟随系统。 */
const Toaster = ({ ...props }: ToasterProps) => (
  <Sonner
    theme="system"
    position="top-right"
    className="toaster group"
    toastOptions={{ unstyled: true }}
    {...props}
  />
)

export { Toaster }

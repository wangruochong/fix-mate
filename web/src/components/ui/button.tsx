import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

/**
 * 按钮变体对应设计稿:
 * default 主色实心;outline 白底描边(原型的普通按钮);good 绿色确认;danger 红字描边;
 * urgent 橙字描边;ghost 无边框;secondary/destructive/link 保留给 shadcn 组件内部使用。
 */
const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center rounded-md border border-transparent bg-clip-padding font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-45 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:brightness-110",
        outline: "border-border bg-card hover:border-faint hover:bg-panel-2",
        good: "bg-success text-white hover:brightness-105",
        danger: "border-danger/35 bg-card text-danger hover:bg-danger-soft",
        urgent: "border-urgent/40 bg-card text-urgent hover:bg-urgent-soft",
        ghost: "text-muted-foreground hover:bg-subtle hover:text-foreground",
        secondary: "bg-secondary text-secondary-foreground hover:bg-secondary/80",
        destructive: "bg-danger-soft text-danger hover:bg-danger-soft/70",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-[34px] gap-1.5 px-3.5 text-[13.5px] [&_svg]:size-4",
        sm: "h-7 gap-1.5 px-2.5 text-[12.5px] [&_svg]:size-3.5",
        lg: "h-[38px] gap-1.5 px-[18px] text-[13.5px] [&_svg]:size-4",
        icon: "size-[34px] rounded-md text-muted-foreground hover:bg-subtle hover:text-foreground [&_svg]:size-[18px]",
        "icon-sm":
          "size-7 rounded-md border-border bg-card text-muted-foreground hover:border-primary hover:bg-primary-soft hover:text-primary [&_svg]:size-3.5",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }

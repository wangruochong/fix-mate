import { Bell, FolderOpen, MessageSquare, PartyPopper, Rocket, User, type LucideIcon } from 'lucide-react'
import { Switch } from '@/components/common/switch'
import { Tag } from '@/components/common/tag'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { PageContainer, PageHeader } from '@/components/page'
import { useUi } from '@/store/ui'

/** 设置项左侧的图标方块。 */
function SettingIcon({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <div className="grid size-[38px] shrink-0 place-items-center rounded-lg bg-primary-soft text-primary">
      <Icon className="size-[18px]" />
    </div>
  )
}

function SettingRow({
  icon,
  title,
  desc,
  children,
  below,
}: {
  icon: LucideIcon
  title: string
  desc: string
  children?: React.ReactNode
  below?: React.ReactNode
}) {
  return (
    <div className="flex flex-wrap items-center gap-3.5 border-b py-4 last:border-b-0">
      <SettingIcon icon={icon} />
      <div className="min-w-0 flex-1">
        <b className="block font-semibold">{title}</b>
        <span className="text-[12.5px] text-muted-foreground">{desc}</span>
      </div>
      {children}
      {below && <div className="mt-2.5 grid w-full grid-cols-2 gap-2.5">{below}</div>}
    </div>
  )
}

const field = 'h-9 rounded-md bg-card px-3 text-sm md:text-sm dark:bg-card'

/** 账号、仓库与打包配置。首次启动页和设置页共用。目前只是静态展示,不接后端。 */
function ConfigRows() {
  return (
    <>
      <SettingRow icon={MessageSquare} title="飞书账号" desc="已授权 · 用于拉取分配给你的缺陷、回写状态与评论">
        <Tag tone="good">已连接</Tag>
        <Button size="sm" variant="outline">
          重新授权
        </Button>
      </SettingRow>
      <SettingRow icon={User} title="Git 身份" desc="使用本机 git 配置 · user.name / user.email 已检测">
        <Tag tone="good">已检测</Tag>
      </SettingRow>
      <SettingRow
        icon={FolderOpen}
        title="工作仓库"
        desc="FixMate 只会在这个仓库里创建临时分支和提交"
        below={
          <>
            <Input className={field} readOnly defaultValue="~/Documents/MBO/mbo-android" aria-label="工作仓库路径" />
            <select className={`${field} rounded-md border border-input`} aria-label="主分支" defaultValue="main">
              <option value="main">主分支:main</option>
              <option value="develop">develop</option>
            </select>
          </>
        }
      >
        <Button size="sm" variant="outline">
          选择文件夹…
        </Button>
      </SettingRow>
      <SettingRow
        icon={Rocket}
        title="Jenkins 打包"
        desc="接受方案并 push 后,通过 REST API 触发 OTA 并记录版本号"
        below={
          <>
            <Input className={field} placeholder="Jenkins 地址" defaultValue="https://jenkins.mbo.local" aria-label="Jenkins 地址" />
            <Input className={field} placeholder="Job 名称" defaultValue="android-ota" aria-label="Job 名称" />
            <Input className={field} placeholder="用户名" defaultValue="ci-bot" aria-label="用户名" />
            <Input className={field} type="password" placeholder="API Token" defaultValue="••••••••••" aria-label="API Token" />
          </>
        }
      >
        <Button size="sm" variant="outline">
          测试连接
        </Button>
      </SettingRow>
    </>
  )
}

const Section = ({ children }: { children: React.ReactNode }) => (
  <div className="mb-4 rounded-xl border bg-card px-5 py-1.5">{children}</div>
)

export function SettingsPage() {
  return (
    <PageContainer className="max-w-[760px]">
      <PageHeader title="设置" desc="账号、仓库与打包配置" />
      <Section>
        <ConfigRows />
      </Section>
      <Section>
        <SettingRow icon={Bell} title="收到新缺陷时通知" desc="应用内弹窗 + 系统通知">
          <Switch defaultChecked label="收到新缺陷时通知" />
        </SettingRow>
        <SettingRow icon={PartyPopper} title="清单处理完成时通知" desc="当前清单里的缺陷都处理完后提醒你">
          <Switch defaultChecked label="清单处理完成时通知" />
        </SettingRow>
      </Section>
    </PageContainer>
  )
}

export function OnboardPage() {
  const go = useUi((s) => s.go)
  return (
    <PageContainer className="max-w-[760px]">
      <div className="mt-[30px] mb-5 text-center">
        <div className="mx-auto mb-4 grid size-14 place-items-center rounded-[17px] bg-gradient-to-br from-[#7a7af0] to-[#4b4bc8] text-[28px] font-extrabold text-white shadow-[0_6px_16px_rgb(91_91_214/0.35)]">
          F
        </div>
        <h1 className="text-[28px] font-bold">欢迎使用 FixMate</h1>
        <p className="mt-1.5 text-muted-foreground">自动拉取飞书缺陷,让 AI 帮你修,你只负责审核。</p>
      </div>
      <Section>
        <ConfigRows />
      </Section>
      <div className="text-center">
        <Button size="lg" onClick={() => go('work')}>
          开始使用
        </Button>
      </div>
    </PageContainer>
  )
}

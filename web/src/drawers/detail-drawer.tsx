import { ExternalLink, MessageSquare, X } from 'lucide-react'
import { useAppData } from '@/api/queries'
import { Card, CardTitle } from '@/components/common/feedback'
import { PriorityDot, StateBadge } from '@/components/common/defect-bits'
import { Tag } from '@/components/common/tag'
import { Drawer } from '@/components/drawer'
import { Button } from '@/components/ui/button'
import { UrgentButton } from '@/components/urgent-button'
import { isInUrgent } from '@/lib/defect'
import { timeAgo } from '@/lib/format'
import { useUi } from '@/store/ui'
import { isUndone, type Defect } from '@/types/defect'
import { ActionBar } from './detail/action-bar'
import { ListBox } from './detail/list-box'
import { StateBody } from './detail/state-body'

const feishuUrl = (d: Defect) => `https://mbo.feishu.cn/project/bug/detail/${d.id}`

/** 缺陷详情:占半屏的右侧侧栏,头部、可滚动主体和底部操作栏三段。 */
export function DetailDrawer() {
  const drawer = useUi((s) => s.drawer)
  const closeDrawer = useUi((s) => s.closeDrawer)
  const { lists, defectMap } = useAppData()
  const open = drawer?.kind === 'detail'
  const defect = open ? defectMap.get(drawer.defectId) : undefined

  return (
    <Drawer open={open && !!defect} onClose={closeDrawer}>
      {defect && (
        <>
          <div className="flex flex-none items-center gap-2.5 border-b px-5 py-[13px]">
            <span className="font-mono text-xs text-muted-foreground">{defect.id}</span>
            <StateBadge defect={defect} lists={lists} />
            <PriorityDot priority={defect.priority} />
            {isInUrgent(lists, defect.id) && isUndone(defect) && <Tag tone="urgent">紧急</Tag>}
            <span className="flex-1" />
            <UrgentButton defect={defect} />
            <Button
              variant="outline"
              size="sm"
              nativeButton={false}
              render={<a href={feishuUrl(defect)} target="_blank" rel="noreferrer" title={feishuUrl(defect)} />}
            >
              <ExternalLink />
              在飞书中打开
            </Button>
            <Button variant="ghost" size="icon" onClick={closeDrawer} title="关闭 (Esc)" aria-label="关闭">
              <X />
            </Button>
          </div>

          {/* 切换缺陷时重置滚动位置 */}
          <div key={defect.id} className="flex-1 overflow-auto px-6 pt-[22px] pb-[30px]">
            <div className="flex flex-col gap-3.5">
              <div>
                <h1 className="line-clamp-2 text-[21px] leading-snug font-semibold tracking-[0.2px]" title={defect.title}>
                  {defect.title}
                </h1>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  <Tag>{defect.type}</Tag>
                  <Tag>报告人 {defect.reporter}</Tag>
                  <Tag>{timeAgo(defect.createdAt)}</Tag>
                </div>
              </div>

              <div className="flex flex-col gap-[9px] rounded-lg border bg-panel-2 px-[15px] py-[13px]">
                <MetaRow label="关联需求" value={defect.requirement} />
                <MetaRow label="规划版本" value={defect.version} />
              </div>

              <ListBox defect={defect} lists={lists} />

              <Card>
                <CardTitle icon={MessageSquare} sub="来自飞书">
                  缺陷描述
                </CardTitle>
                <p className="opacity-90">{defect.description}</p>
              </Card>

              <StateBody defect={defect} lists={lists} defectMap={defectMap} />
            </div>
          </div>

          <ActionBar defect={defect} lists={lists} defectMap={defectMap} />
        </>
      )}
    </Drawer>
  )
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-3.5 text-[13px]">
      <label className="w-[58px] flex-none pt-px text-xs text-faint">{label}</label>
      <span className="line-clamp-2 min-w-0 flex-1 leading-normal" title={value}>
        {value}
      </span>
    </div>
  )
}

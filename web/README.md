# FixMate 前端

React 19 + TypeScript + Vite + Tailwind 4 + shadcn/ui。设计见 `../docs/design.md`,界面原型见 `../prototype/index.html`。

## 运行

```bash
npm install
npm run dev        # 开发,默认使用假接口,打开 http://localhost:5173
npm test           # 单元测试(模拟引擎、纯逻辑)
npm run e2e        # 端到端测试(会自动启动开发服务,需先 npx playwright install chromium)
npm run build      # 正式构建,产物里不含假数据
```

## 假接口

开发时默认由 **MSW** 在浏览器里拦截 `/api/...`,背后是 `src/mock/engine.ts` 里的模拟引擎:
调度、紧急插队、暂停恢复、接受流程都在里面,AI 处理用定时器推进。页面左下角有调试面板
(首次启动、模拟新缺陷、批量生成 300 条、重置数据),正式构建不会出现。

- 关闭假接口,连真实后端:`VITE_USE_MOCK=false npm run dev`,后端地址用 `VITE_API_BASE` 指定(默认同源)。
- 种子数据在 `src/mock/seed.ts`,批量数据在 `src/mock/bulk.ts`(faker)。

## 目录

```
src/
  api/       请求封装、操作函数(actions)、数据查询(queries)、SSE 订阅(events)
  types/     缺陷、清单、事件的类型,是前后端的数据约定
  mock/      假接口:handlers、引擎 engine、种子数据 seed
  lib/       纯函数(状态文案、搜索、清单编辑筛选等),都有单测
  store/     纯界面状态(当前页、侧栏、弹窗),业务数据不放在这里
  components/ 通用组件;ui/ 是 shadcn 生成的基础组件
  layout/ pages/ drawers/ dialogs/   外壳、页面、右侧栏、弹窗
```

## 接口约定

前端只依赖下面这些接口(`src/mock/handlers.ts` 是参考实现)。业务规则全部在后端,前端只发请求、渲染结果。

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/defects` `/api/defects/:id` | 缺陷列表、详情,类型见 `types/defect.ts` |
| GET | `/api/lists` | 清单列表,每个清单带由缺陷状态推导的 `state` |
| GET | `/api/notifications` | 通知列表 |
| POST | `/api/notifications/read` | 全部标为已读 |
| POST | `/api/lists` | 新建清单 `{name, defectIds}`,返回 `{id}` |
| PATCH / DELETE | `/api/lists/:id` | 编辑、删除清单 |
| POST | `/api/lists/:id/start` `pause` `prioritize` | 开始或继续、暂停、优先处理 |
| POST / DELETE | `/api/lists/:id/defects[/:defectId]` | 把缺陷加入、移出清单 |
| POST | `/api/defects/:id/pause` `resume` | 暂停、继续修复 |
| POST | `/api/defects/:id/urgent` | 立即处理 `{position: 'front' \| 'back'}` |
| POST | `/api/defects/:id/recheck` `accept` | 复核、接受 |
| POST | `/api/defects/:id/reject` `pass` | 拒绝 `{keepChanges, reason?}`、跳过 `{reason}` |
| GET (SSE) | `/api/events` | 事件流,事件类型见 `types/events.ts`:`changed`(数据变了,前端重新获取)、`toast`(提示)、`accept-progress`(接受流程进度) |

出错时返回非 2xx 和 `{message}`,前端会弹出这条中文提示。

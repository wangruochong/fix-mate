# FixMate 后端

Python 3.12 + FastAPI + LangGraph + Claude Code。设计见 `../docs/design.md`,前端见 `../web/README.md`。

## 运行

需要 [uv](https://docs.astral.sh/uv/)(它会自己准备 Python 3.12)。

```bash
cd backend
uv sync                      # 安装依赖
uv run pytest                # 测试(不调用 AI,不花钱)
uv run ruff check .          # 代码检查
```

**开发模式**(假的飞书和 Jenkins,AI 改代码默认也是假的;自动创建一个沙盒 git 仓库,不碰任何真实项目):

```bash
FIXMATE_ENV=dev uv run fix-mate          # http://127.0.0.1:8000
# 另开一个终端启动前端,连这个后端:
cd ../web && VITE_USE_MOCK=false npm run dev
```

先在 `web/` 里 `npm run build` 的话,后端会直接提供页面,**一个进程就够了**:打开 http://127.0.0.1:8000。

**让真正的 Claude Code 改代码**(会花钱,每个缺陷有费用上限;需要本机已安装并登录 Claude Code):

```bash
FIXMATE_ENV=dev FIXMATE_FIXER=claude FIXMATE_REPO=/path/to/一个专用的克隆 uv run fix-mate
```

> `FIXMATE_REPO` 必须是 **FixMate 专用的克隆**(不是你日常开发的目录)。接受方案时会在里面切 main、
> cherry-pick 并 **push 到它的 origin**。用一个一次性的克隆试用,别指向真实项目的主仓库。

真实的飞书和 Jenkins 还没有实现,所以目前非开发模式的 graph 引擎会拒绝启动(见下面「还没做的」)。

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `FIXMATE_ENV` | `prod` | `dev` 时提供 `/api/dev/*` 调试接口、使用假的飞书和 Jenkins、可自动创建沙盒仓库 |
| `FIXMATE_DATA_DIR` | `~/.fixmate` | 数据目录:业务库 `fixmate.db`、检查点库 `checkpoints.db`、工作目录 `worktrees/` |
| `FIXMATE_ENGINE` | `graph` | `graph` 是真正的引擎;`stub` 是定时器模拟(只用于早期演示和测试) |
| `FIXMATE_FIXER` | `fake` | `fake` 假的改代码(不花钱);`claude` 真正的 Claude Code |
| `FIXMATE_REPO` | 无 | graph 引擎用的专用仓库克隆。dev 模式不设置就用自动创建的沙盒仓库 |
| `FIXMATE_SEED` | dev 下为 1 | 数据库为空时是否灌入演示数据 |
| `FIXMATE_HOST` / `FIXMATE_PORT` | `127.0.0.1` / `8000` | 监听地址。**只监听本机,不要改成 0.0.0.0** |
| `FIXMATE_WEB_DIR` | `../web/dist` | 前端构建产物目录 |
| `FIXMATE_CLAUDE_MODEL` | 默认模型 | 例如 `haiku`(便宜,适合试用) |
| `FIXMATE_CLAUDE_ASSESS_BUDGET` / `_FIX_BUDGET` | `0.5` / `3.0` | 判断、改代码各自的费用上限(美元) |
| `FIXMATE_CLAUDE_TIMEOUT` | `1200` | 单次改代码的整体超时(秒) |
| `FIXMATE_STUB_SPEED` | `1` | 假执行器的速度倍数,测试里调大 |

## 代码地图

```
src/fix_mate/
  domain/     纯业务规则,没有任何 IO。models.py 是和前端 web/src/types 一一对应的数据结构;
              schedule.py 回答「现在该暂停谁、该开始谁」
  engine/     ★ AI 引擎(LangGraph)。逐行 review 建议按下面的顺序读
  adapters/   外部系统的具体实现:git、Claude Code、假的飞书/Jenkins、开发用沙盒仓库
  services/   调度器和用户操作的入口(锁、消息队列在这里)
  store/      SQLite 仓储,所有 SQL 都在这里
  api/        FastAPI 路由、事件流、本地访问保护
```

### 阅读 AI 引擎的顺序(`engine/`)

1. `external.py`:引擎依赖的外部系统有哪些(改代码、git、飞书、Jenkins),都只是接口。
2. `fix_graph.py`:**修复图**。文件开头有流程图,四个节点各做一件事;「暂停和恢复」「节点必须能安全重跑」的规则都写在开头。
3. `runner.py`:怎么启动、暂停、恢复一个图,怎么把进度汇报给调度器。
4. `accept_graph.py`:**接受图**。7 步固定流程;开头写了为什么进度存业务库、哪些步骤不能重做。
5. `accepter.py`:驱动接受图,失败时说清楚卡在哪一步。
6. `ports.py`:调度器和执行器之间的边界;`stub.py` 是早期的定时器模拟,可以不看。

需要重点把关的几处:`fix_graph.py` 的暂停规则、`accept_graph.py` 的 `REPEAT_SAFE`(哪些步骤不能重做)、
`adapters/git.py`(所有 git 操作)、`adapters/claude_guard.py`(限制 AI 能碰什么,因为缺陷内容不可信)。

## 测试

- `uv run pytest`:约 200 条,不调用真实 AI。包含用**真实 git 仓库**的测试(临时目录里建 origin、专用克隆和同事的克隆)。
- `tests/test_contract.py`:自动比对 Python 模型和前端 TypeScript 类型,任何一边改了字段就会失败。
- 真实的 Claude Code 集成测试默认跳过:
  `FIXMATE_RUN_CLAUDE_TESTS=1 FIXMATE_CLAUDE_MODEL=haiku uv run pytest tests/test_claude_integration.py -s`
  (花费很小,每个测试有费用上限)。
- 前后端联调:`cd ../web && npm run e2e`,同一套浏览器测试会分别对假接口和真实后端各跑一遍。

## 还没做的

- 真实的飞书(拉取缺陷、标记已解决、评论)和 Jenkins(打 OTA)。接口已定(`engine/external.py`),只缺实现。
- 「拒绝并保留修改」:把改动放进你日常的工作区(目前保留分支,没有写进工作区)。
- 复核的真实做法(目前是占位实现,不改动方案)、失败状态的完整设计(目前接受失败保持待审核并显示卡在哪一步)。

# FixMate

自动拉取分配给你的飞书缺陷,让 AI 通过修改代码来修复,你只负责审核。

```
docs/design.md   设计文档(产品规则、状态流转、技术方向、风险),所有结论以它为准
prototype/       最初的界面原型(单文件 HTML),只作参考
web/             前端:React + TypeScript + Vite + shadcn/ui,见 web/README.md
backend/         后端和 AI 引擎:Python + FastAPI + LangGraph + Claude Code,见 backend/README.md
```

## 快速体验

**只看界面**(不需要后端,数据是浏览器里的假数据):

```bash
cd web && npm install && npm run dev
```

**完整的一套**(真实的后端、真实的 AI 引擎和 git 沙盒仓库,只有「改代码」和飞书、Jenkins 是假的):

```bash
cd web && npm install && npm run build         # 构建前端
cd ../backend && uv sync
FIXMATE_ENV=dev uv run fix-mate                # 打开 http://127.0.0.1:8000
```

## 现状

- 已完成:前端全部界面;后端的清单调度、紧急插队、暂停恢复;AI 引擎的修复流程和接受流程;
  真实的 git worktree 操作;真实的 Claude Code 集成(带安全限制)。
- 还没有:真实的飞书和 Jenkins、「拒绝并保留修改」。详见 `backend/README.md` 末尾和设计文档第 11 节。

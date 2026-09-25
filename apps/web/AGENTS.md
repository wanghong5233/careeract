<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## CareerAct web boundaries

- 工作台围绕职业项目、材料、岗位和任务组织；assistant-ui 是交互组件，不决定整个信息架构。
- 浏览器只走同源 BFF；领域规则留在 FastAPI，JWT、数据库凭据和 BYOK 不进入客户端 bundle。
- 修改 React 数据流、复杂组件或性能时按需使用 `careeract-web`；认证问题使用 `careeract-auth`。
  纯文案或简单样式调整不需要加载整套 Skills。
- 先复用现有 shadcn/ui 组件；长任务 UI 要区分等待人工、失败、取消与完成，不以流结束判成功。
- 有行为的 UI 改动除类型检查外，还要在可运行环境验证用户路径；工具不可用时明确记录未验收。

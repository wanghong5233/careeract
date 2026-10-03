<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## CareerAct web boundaries

- Web 是 CareerAct 的 Agent 产品壳：Agent 委托是主要入口，职业项目、材料、岗位和任务是
  Agent 可调用的能力与领域对象；按需打开的工作面承载上下文、成果、审阅和授权。assistant-ui
  只是交互组件，不决定产品形态。
- 产品布局遵循[当前形态设计](../../docs/topics/workspace/DESIGN.md#codex-骨架与标签工作区)：以 Codex 骨架为主要参照，角色层可选。
  完整能力通过 Agent 委托、项目/对话、关联内容和能力发现到达；不以模块墙或长表单组织首页。
- 页面设计与审阅遵循[产品设计原则](../../docs/handbook/DESIGN_PRINCIPLES.md)；具体任务从
  [STATUS](../../docs/handbook/STATUS.md)进入当前专题，候选设计不等于已确认或已实现能力。
- 浏览器只走同源 BFF；领域规则留在 FastAPI，JWT、数据库凭据和 BYOK 不进入客户端 bundle。
- 修改 React 数据流、复杂组件或性能时按需使用 `careeract-web`；认证问题使用 `careeract-auth`。
  纯文案或简单样式调整不需要加载整套 Skills。
- 先复用现有 shadcn/ui 组件；长任务 UI 要区分等待人工、失败、取消与完成，不以流结束判成功。
- 有行为的 UI 改动除类型检查外，还要在可运行环境验证用户路径；工具不可用时明确记录未验收。
- `npm run test` 使用 Node 内置测试运行实际状态/请求源码；BFF 的身份与上游替身不代表真实认证集成通过。
  异步或导航修改需覆盖旧响应、取消、输入保留或失败语义中实际受影响的行为，再做可见页面验收。
- ESLint 模板豁免限定到具体文件和规则；扩展豁免前用 Git 历史核实模板来源并记录理由，
  不对全部自有组件关闭 React Hook 或可访问性规则。

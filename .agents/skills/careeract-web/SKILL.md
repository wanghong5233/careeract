---
name: careeract-web
description: Implement or review CareerAct React/Next.js workspace data flows, complex interactive components and performance issues. Apply to server/client boundaries, async task UX and material/job views; skip copy-only edits, simple styling and backend-only tasks.
---

# CareerAct Web 工程

读取 [前端指令](../../../apps/web/AGENTS.md) 和本次涉及的现有组件。
先确认锁文件中的 Next.js/React 版本，按前端指令读取安装包内相应文档；缺少本地文档时查匹配版本的官方资料，
不把最新示例直接套入当前版本。来源与适配见 [Skills 说明](../../../docs/SKILLS.md)。

## 先决定数据和状态归谁

- 页面服务于职业项目、材料、岗位和任务；复用现有工作台与 shadcn/ui，避免重建组件体系。
- 领域状态由 API 持有；UI 临时状态与可恢复的业务任务分开，不用聊天消息或组件状态代替数据库记录。
- 把客户端边界放在确实需要交互的位置；不要仅因一个按钮把整页与服务端依赖移到客户端。
- 浏览器只访问同源 BFF。私密凭据、JWT 签发与数据库实现留在服务端；不为绕过 CORS 直接公开内部服务。

## 数据请求与性能

- 找出请求依赖后再并行：独立读取可同时发起，授权检查和有先后语义的外部写操作不能随意并行。
- 不跨用户缓存私有材料或任务响应。需要缓存时明确身份、权限、材料版本、失效与退出登录后的清理。
- 只传客户端需要的可序列化字段；大型编辑器/PDF 等组件按实际页面使用延迟加载，先确认当前库的 SSR 限制。
- 避免 Effect 反复复制可直接计算的派生状态；异步切换资源时处理旧请求覆盖新结果和取消订阅。
- 先看可观察的瀑布、包体积或渲染瓶颈，不提前为小组件遍布 memo、缓存和微优化。
- 不因教程引入新的请求库或把持久任务放进 Next.js `after()`；现有工具能解决时优先复用。

## 任务交互

- 对有异步行为的视图区分加载、空态、失败、等待人工、取消与完成；流断开不等于业务成功或失败。
- 恢复页面时查询业务状态，不盲目重放提交；UI 禁用按钮不能替代后端幂等与授权。
- 表单有明确 label、错误反馈和键盘路径；弹窗/人工接管需要焦点处理。复用组件能力，不先建新的设计系统。
- 对不可逆操作显示材料版本与动作范围，只有服务端验收结果才能显示“已完成”。

## 验收

按 [开发指南](../../../docs/DEVELOPMENT.md) 选择检查。涉及交互时在实际页面操作关键路径，
包括切换资源、失败/等待状态和窄屏布局；用当前可用浏览器工具，不自动安装另一套工具。
无法运行时明确未验收的交互，不把 typecheck 或截图当作业务完成证据。

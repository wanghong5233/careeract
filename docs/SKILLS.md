# 项目 Skills

这三个 Skill 是 CareerAct 自行编写的精简适配，不是原样安装或镜像上游插件。
它们借鉴下列已审阅资料的工程方法，并通过本项目代码入口、约束和验收方式落地。
没有安装全局插件、MCP、Hooks 或附带脚本，也没有改变产品运行依赖。

## 选择与发现

| Skill | 何时读取 | 不用于 |
| --- | --- | --- |
| [careeract-debug](../.agents/skills/careeract-debug/SKILL.md) | 跨服务故障、原因不清的失败、重复修复无效 | 明确的一行错误、一般问答 |
| [careeract-web](../.agents/skills/careeract-web/SKILL.md) | React/Next 数据流、复杂工作台交互、性能问题 | 纯文案、简单样式、后端功能 |
| [careeract-auth](../.agents/skills/careeract-auth/SKILL.md) | Better Auth、BFF/JWT/JWKS、认证 Schema | 一般业务 CRUD、从零换认证方案 |

Codex 支持仓库根 `.agents/skills/`；新会话确认技能列表中是否可见，也可用 `$careeract-auth` 等点名。
其他 Agent 的自动发现机制不保证相同：按本文件链接显式读取即可，不为尚未使用的工具复制整套配置。
根 AGENTS 不要求全量加载。Skill 的任务描述用于选择，正文只在相关任务读取。

## 来源与适配

审阅日期：2026-09-25。下面是来源链接，不是运行时自动下载入口；本地正文随 Git 版本管理，
不会因远端 `main` 更新而静默改变。未复制第三方脚本或规则库，不宣称已经安装上游完整能力。

| 资料 | 采用的经验 | 本项目适配 |
| --- | --- | --- |
| [Superpowers systematic-debugging](https://github.com/obra/superpowers/blob/main/skills/systematic-debugging/SKILL.md) | 复现、逐层证据、单一假设、最小验证 | 不强制所有问题走四阶段；不自动打印环境变量；不依赖其他 Superpowers Skills |
| [Vercel React Best Practices](https://github.com/vercel-labs/agent-skills/blob/main/skills/react-best-practices/SKILL.md) | 避免请求瀑布、缩小客户端边界、按影响优化 | 保留 BFF 与领域分层；私有数据缓存必须隔离；不新增 SWR 等依赖来满足示例 |
| [Better Auth Best Practices](https://github.com/better-auth/skills/blob/main/better-auth/best-practices/SKILL.md) | 按已安装版本查文档、核对插件与会话 Schema | 使用 Alembic，不照抄 `auth@latest migrate`；不重新初始化已有认证 |

编写与加载方式参考 [OpenAI Skills 文档](https://learn.chatgpt.com/docs/build-skills)。
技能是开发指导，不是权限来源，不能覆盖用户授权、项目边界或替代可执行测试。

## 暂不引入

- Playwright CLI Skill：目前可复用已有浏览器工具；需要独立 CLI 时再核对 Windows/WSL 和 Bash 依赖。
- Web Design Guidelines：真实页面形成后再做 UI/可访问性专项评审，不在每次改动拉取整套远端规则。
- gh-fix-ci、安全评审 Skills：出现相应任务再评估，不因为已有 CI 就引入额外工作流程。
- Skills 大合集、自动部署、强制多 Agent、每次改动强制 TDD/规划：当前没有足够收益支撑其成本。

## 如何维护与试用

先看下一项实际任务是否需要新 Skill；几条命令优先放开发指南。只有重复、非显然、需要判断的流程才提炼。
引入第三方文件时先审正文、引用、脚本、依赖和许可，并固定来源版本；不能只看 Star 或安装量。
若修改上游内容，明确标注本地适配，不冒充未修改的官方版本。

初始化阶段检查以下预期；自动选择和执行收益需在后续真实会话验证，不能把静态检查当作行为测试：

| 示例任务 | 预期 |
| --- | --- |
| BFF 返回 401，API 直连与 Web 会话表现不一致 | auth；若跨层原因不清再叠加 debug |
| 材料列表切换后仍显示旧用户数据 | web；检查身份/缓存边界，必要时 auth |
| Temporal 已接单但 Browser 没动作，多次改配置无效 | debug |
| 改 README 错字或按钮文案 | 不加载上述三个 Skill |
| 开发 API 业务规则但未涉及认证 | 不因 Python/API 关键词触发 auth 或 web |

观察是否减少漏项与返工；若误触发、指令冲突或增加无效操作，收窄描述或移除。
不添加固定“必须安装多少个”的目标，也不预置空 references/scripts 目录。

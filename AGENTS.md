# CareerAct Agent Instructions

本地存在 `docs/PRD.md` 与 `docs/ARCHITECTURE.md` 时先读。产品是职业
Agent Workspace，不是聊天应用、通用 Computer Use 平台或 RAG 项目。

## Architecture boundaries

- `apps/web`：Next.js 工作台、Better Auth、同源 BFF 和 Agent 交互组件。
- `services/api/domain`：无框架依赖的职业领域对象与规则。
- `services/api/application`：用例、事务边界和外部能力端口。
- `services/api/infrastructure`：数据库、AgentOS、模型、认证和对象存储实现。
- `services/api/routes`：REST / AG-UI 入口，不写业务规则。
- `services/worker/workflows`：确定性的 Temporal 编排，不执行网络或文件 I/O。
- `services/worker/activities`：调用 API、Agent、浏览器和外部渠道的副作用。
- `services/browser`：会话租约、Playwright、browser-use 和站点适配。

PostgreSQL 中的 CareerAct 领域数据是业务真相。Agent Run、聊天线程、Temporal History 和浏览器页面都不能替代领域状态。
新增产品 REST 路由统一放在 `/api/v1`，并遵循 `services/api/routes/README.md`
中的错误、分页、并发控制与幂等约定。

## Reliability

- 外部写操作必须记录授权、尝试和结果证据。
- 结果不确定的投递或消息发送不得自动重试。
- browser-use 的成功必须由确定性读取或站点适配器再次核验。
- 人工接管、Playwright 和 browser-use 对同一会话互斥。
- 长任务必须具有明确的 accepted、running、waiting、failed、timed_out、completed 状态。
- 不捕获宽泛异常，不用空结果掩盖失败，不硬编码密钥。

## Dependencies and vendor

- Agno 与 browser-use 来自项目所有者的 GitHub Fork，并通过 `git subtree` 放在 `vendor/`。
- 业务能力写在 CareerAct 服务中；只有确认是上游缺陷时才修改 `vendor/`。
- vendor 修改单独提交，并记录对应上游提交；可复用修复优先回馈上游。
- 其他依赖通过锁文件和固定 Docker 镜像使用，不因方便而复制框架源码。
- 升级 Better Auth 时必须同步核对并新增认证 Schema 的 Alembic migration；
  不允许覆盖已有 revision 或依赖 PostgreSQL 首次初始化脚本改表。

## Verification

修改后只运行与改动相关的最小检查；提交前运行：

```powershell
uv sync --all-packages
uv run ruff format --check services tests
uv run ruff check services tests
uv run mypy services tests
uv run pytest
Set-Location apps/web
npm run lint
npm run typecheck
npm run build
```

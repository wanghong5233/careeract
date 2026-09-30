# CareerAct Agent Instructions

产品是职业 Agent Workspace，不是聊天应用、通用 Computer Use 平台或 RAG 项目。

## Start here

- 新会话先读 [当前状态](docs/handbook/STATUS.md)，确认本次任务与下一步；开发、启动和验收看
  [开发指南](docs/handbook/DEVELOPMENT.md)。不要把规划中的能力当作已经实现。
- 首次接手或修改产品/架构时，若本地有 `docs/PRD.md` 与 `docs/ARCHITECTURE.md`，先读；
  同一任务后续只读相关章节。它们是未公开的长期设计，当前交付范围以 STATUS 为准。
- 没有私人文档的新克隆可依据本文件、STATUS 和代码开始开发；确实缺少业务定义时再询问，
  不搜索项目所有者的上级私人目录来补上下文。
- 改哪个服务，读该目录适用的 `AGENTS.md` 和相关职责 README；不用遍历整个 vendor。
- 项目 Skills 在 `.agents/skills/`，仅按任务匹配加载；来源、边界和维护方式见
  [Skills 说明](docs/handbook/SKILLS.md)。未自动发现时可按该说明读取对应入口，不假装已调用。

## Working agreements

- 先看工作区已有改动；不覆盖他人修改。默认不 commit、push 或创建 PR，除非用户要求。
- 小改动直接处理；跨服务、行为不明确或有外部副作用的任务，先明确范围、验收和风险。
  重要专题在 `docs/topics/<name>/` 集中维护；工作组织与文档治理按需读 `careeract-engineering`。
- 按[单人开发流程](docs/handbook/DEVELOPMENT.md#单人开发流程)一次推进一个可验收目标；
  常规顺序开发默认沿当前主线，隔离实验或并行工作再用短期分支，不强制每项任务建立 PR。
- 优先复用现有组件、接口和检查；不为未来功能预建抽象，不因 Skill 示例添加依赖或换栈。
- 新的事实、已验证能力或下一步发生变化时更新 STATUS；只记录结果和证据，不抄聊天日志。
- 本地检查和产品真实外部操作分开：开发授权不等于向招聘方发送消息、提交申请、购买或部署。
- 密钥、Cookie、真实简历和招聘截图不进入 Git、公开日志或文档；诊断配置只报告是否存在与脱敏差异。
- 涉及网页交互验收时优先使用可见的 Computer Use 浏览器，让用户能看到操作；终端检查正常执行。
- 首次克隆按开发指南启用 `.githooks`；提交须通过 Gitleaks 暂存区扫描，不绕过 hook，
  不未经核实扩大 `.gitleaksignore`。CI 检查不能阻止本地秘密先被推送，优先本地拦截。

## Documentation

- PRD 只写需求与业务验收，不混入详细设计或未验证承诺；讨论建议不等于已确认需求。
- 改变 PRD 范围、优先级或能力承诺前先给出改稿与依据，由用户确认；已有明确授权不重复询问。
- 优先最小更新现有文档，一类信息只维护一处，不按对话轮次新增文件。
- `docs/` 顶层保留 PRD/ARCHITECTURE；全项目手册放 `docs/handbook/`，具体专题放 `docs/topics/`。
  职责、维护与迁移规则见[文档维护](docs/handbook/DEVELOPMENT.md#文档维护)。
- 私人设计、研究和真实资料保持 Git 忽略；公开文档逐文件放行，不整体开放目录。

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

产品身份由 Better Auth 管理，框架运维权限不授予 CareerAct 产品管理权。
业务读取/写入按服务端验证的 `user_id` 校验归属；资源 ID 和模型网关凭据不是用户授权。
框架管理凭据与业务运行凭据分离，实施顺序及验收见 [开发指南](docs/handbook/DEVELOPMENT.md#身份与权限边界)。

## Reliability

- 外部写操作必须记录授权、尝试和结果证据。
- 结果不确定的投递或消息发送不得自动重试。
- browser-use 的成功必须由确定性读取或站点适配器再次核验。
- 人工接管、Playwright 和 browser-use 对同一会话互斥。
- 长任务必须具有明确的 accepted、running、waiting、failed、timed_out、cancelled、completed 状态。
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
uv sync --frozen --all-packages --group dev
uv run ruff format --check services tests
uv run ruff check services tests
uv run mypy services tests
uv run pytest
Set-Location apps/web
npm run lint
npm run typecheck
npm run build
```

仅文档/Skills 改动检查链接、路径、格式、指令冲突和 Git 忽略边界，无需安装业务依赖或跑全栈。
上述命令是代码提交检查；执行完返回仓库根目录。CI 的版本与环境以 `.github/workflows/ci.yml` 为准。
报告实际执行的检查和结果；未运行、被环境阻塞、使用 mock 与真实集成通过必须分别说明。
区分文档/源码支持、本地验证与目标部署环境验证，不将前者表述为后者。

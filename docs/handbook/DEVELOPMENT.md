# 工程协作与开发手册

## 先找对信息

- 本文是单人开发 SOP 与操作入口；当前范围与下一步见 [STATUS](STATUS.md)，不在此记录每轮结果。
- 稳定架构规则与代码提交检查命令：[AGENTS](../../AGENTS.md)。
- Web：[前端指令](../../apps/web/AGENTS.md)；API：[REST 约定](../../services/api/routes/README.md)。
- 任务：[Workflow 边界](../../services/worker/workflows/README.md)；浏览器：[服务边界](../../services/browser/README.md)。
- 专项流程：[Skills 说明](SKILLS.md)。PRD、详细架构和历史采购材料可能仅在所有者本地存在。

## 单人开发流程

适用于单人维护、学生预算、代表作与自用优先的阶段。用户决定产品方向和重要交互，Agent
负责提出依据、实施、验证及同步文档；已授权范围内的常规工程选择直接推进，不逐步索取批准。

| 环节 | 执行方式 | 必要产物或完成信号 |
| --- | --- | --- |
| 选择工作 | 检查已有改动与 STATUS；按 PRD 价值、依赖、风险和可用时间，默认只推进一个主要目标 | STATUS 的当前、接下来、暂缓；阻塞时记录原因和可恢复条件 |
| 明确问题 | 小修直接处理；重要专题明确目标、范围和可观察的验收条件 | 复用专题 README，不为每项任务生成完整模板 |
| 消除不确定性 | UI 优先用少量效果图或现有页面确认方向，再在正式前端迭代；仅复杂交互按需做最小原型；架构用最小实验；调优用可比较的样本与指标 | 设计已确认或假设有证据；避免维护第二套 UI，模拟结果不冒充真实能力 |
| 实现 | 按一条完整路径小步推进；复用组件，保持服务边界；新发现及时更新方案 | 可运行增量；只拆当前需要的任务，不预建未来模块 |
| 验收 | 依据目标验证成功、失败和适用的隔离/持久化/恢复行为 | 相关检查及可见操作证据，标明 mock、本地或部署环境；未通过不标完成 |
| 收尾与维护 | 审查差异，形成可独立验证的提交单元；同步受影响文档、清理失效内容，再选择下一项 | 实际交付、限制、证据和后续入口；提交、推送、部署仍遵循用户授权 |

这些是循环中的动作，不是固定审批阶段；明确的小修可在一次处理中完成。
常规顺序开发沿主线，隔离实验、并行工作或线上修复再用短期分支；不强制 Sprint、故事点、
逐任务 PR 或固定会议。紧急缺陷插入时，先保存当前上下文，避免工作相互混杂。
提交按目的划分，不按文件或对话拆分；按根 AGENTS 完成检查和凭据扫描，不绕过 hook。
涉及迁移、部署或外部副作用时先明确兼容、数据保留、恢复与结果核验，Git 回退不等于数据回退。

反复返工时检查缺的是需求、上下文、设计确认还是验证手段，改进对应环节；不默认追加规则。
当前任务完成后简短回看是否减少返工和恢复成本，不为复盘另写例行报告。

## 文档维护

文档按作用域组织：PRD/ARCHITECTURE 是长期方向；handbook 是全项目复用的手册；topics
是具体专题的研究、设计与实施依据。状态和公开性是文档属性，不再混作目录分类。

| 内容 | 维护位置 |
| --- | --- |
| 为什么做、需求与业务验收 | `docs/PRD.md`，不记录具体布局、字段实现或本轮任务 |
| 系统边界、技术结构与已确认的关键决策 | `docs/ARCHITECTURE.md`；候选与实验留在相关专题 |
| 项目进度、已验证能力和优先顺序 | [STATUS](STATUS.md)，只维护概要及证据入口，不复制操作参数和任务清单 |
| 工程 SOP、启动与检查方法 | 本指南；修改命令的同时维护对应操作，不把一次运行结果写成永久承诺 |
| 跨页面设计原则 / 技能入口 | [DESIGN_PRINCIPLES](DESIGN_PRINCIPLES.md) / [SKILLS](SKILLS.md) |
| 具体专题的需求细化、方案、原型、研究、实验与验收 | `docs/topics/<name>/`；需要独立推进时从一份 README 起步，其他文件按需添加 |
| 服务约定与实现细节 | 对应服务 README、代码与测试，不在总架构重复展开 |

- 一个事实只有一个维护位置，其他文档链接引用。判断放哪里时先问它服务全项目还是某个专题，
  再区分需求、方案、操作、结果；不按聊天轮次或文件格式建分类。
- 专题 README 写明本次目标、状态、必要任务和结果入口。同一专题持续维护，用小节区分迭代；
  不把整个领域变成一个永远无法验收的大任务，也不为每次小修建新专题。
- 方案标明草案、已确认或已替代，工作标明待办、进行中、阻塞或已完成；两种状态分别表达。
  定稿不等于实现、实现不等于验收。重要决策留理由及证据，调研注明日期与未验证边界。
- 完成后目录留在原处，更新状态；长期有效结论归入对应权威文档，历史结果注明当时版本或日期。
  不另建 active/archive 或平行的管理索引；STATUS 仅链接当前优先事项。
- 用户负责方向与关键决策；Agent 在每次相关交付中维护文档和引用。已知过时内容随任务收尾修正，
  不要求每轮扫描全部历史。文档太长时按读者任务拆分，不按篇幅机械切割。

- 修改 PRD 前呈现相关章节、简要改稿、依据与未验证边界；用户明确授权指定结论后直接更新，
  纠错和链接修复直接处理。保留原有组织与粒度，不将技术方案包装成需求。
- 新文档先确定读者、归属与维护方式，并从现有入口链接；没有实际内容不预建目录或模板。
- 移动文档同步修正链接、引用并移除旧副本；新增公开文档逐文件检查 Git 允许列表。
- 已失效且可由 Git 追溯的文档可删除；私人或未提交的独有依据先保留，不能假设 Git 能恢复。
  迁移私人文档核对内容保留并继续忽略；公开文件逐个放行，不复制真实资料到公开原型或日志。
- AGENTS 保留跨任务边界与入口；工程协作 Skill 按需指导判断，引用本 SOP，不再维护另一套规则。
  可执行的凭据拦截与测试由 hook/脚本负责，不依赖长提示词。

## 环境

下面使用仓库根目录下的 PowerShell。Python/Node/uv 的 CI 基准看
[ci.yml](../../.github/workflows/ci.yml)，依赖版本以 `uv.lock` 和 `apps/web/package-lock.json` 为准。
不要混用 Windows 与 WSL 的虚拟环境或 `node_modules`；选定一侧后在该环境安装依赖。

先只读检查 `docker info`、`docker compose version`、`uv --version`、`node --version`、`npm --version`。
Docker CLI 存在不代表 Linux 引擎已启动。检查可用内存、Docker 虚拟磁盘所在盘与端口冲突；
32GB 开发机可起步，12–16GiB WSL 预算只是待实测的起始建议，不自动修改机器配置。

## 配置与启动

这些是待运行的启动路径，不是已经通过的集成证明。首次下载镜像、依赖和解析模型需要网络与磁盘空间。

1. 仅当文件不存在时创建配置，保留已有密钥：

   ```powershell
   if (-not (Test-Path .env)) { Copy-Item .env.example .env }
   if (-not (Test-Path apps/web/.env.local)) { Copy-Item apps/web/.env.example apps/web/.env.local }
   ```

   参考两个 `.env.example` 填写本地值，替换占位密钥。Web 在 `apps/web` 启动，Python 服务在根目录启动。
   检查 URL、issuer、audience 和数据库地址一致；不得在诊断输出中打印 secret、完整 DSN 或 JWT。

2. 准备锁定依赖并先启动数据库：

   ```powershell
   uv sync --frozen --all-packages --group dev
   npm --prefix apps/web ci
   docker compose up -d postgres
   docker compose ps
   uv run --package careeract-api alembic -c services/api/alembic.ini upgrade head
   ```

   等数据库 healthy 后再迁移。初始化脚本只作用于首次建卷；已有数据库结构必须通过新 Alembic revision 演进。

3. 先启动模型网关并初始化受限服务 Key，再用组合入口启动 Web 与 API：

   ```powershell
   docker compose up -d litellm
   uv run --no-sync python scripts/manage_model_key.py provision
   ```

   网关需先就绪；若初始化报告连接失败，确认就绪后重跑同一命令。脚本保留已有密钥，
   检查同一 Key 的配置，不重置预算或自动扩大权限。详见下文凭据生命周期。

   ```powershell
   npm --prefix apps/web run dev
   ```

   ```powershell
   npm --prefix apps/web run dev:status
   ```

4. 验证模型、持久任务或浏览器时再启动相关组件：

   ```powershell
   docker compose up -d litellm temporal steel
   ```

   以下两个长进程也各占一个终端：

   ```powershell
   uv run --package careeract-worker python -m services.worker.app.main
   ```

   ```powershell
   uv run --package careeract-browser uvicorn services.browser.app.main:app --port 8001 --reload
   ```

   LiteLLM 配置在 `infra/litellm/config.yaml`，当前提供两个服务端模型别名：
   `careeract-default`（阿里百炼兼容接口）和 `careeract-openai`（OpenAI）。在根目录 `.env`
   填写 `DASHSCOPE_API_KEY` 与 `OPENAI_API_KEY` 后，按 `LITELLM_MODEL` 选择默认别名；密钥只放
   在服务端环境，不复制到 `apps/web/.env.local`。容器启动不能证明模型可调用，必须完成一次真实
   请求和流式响应验收。Docling 的模型下载、离线资源与中文字体也需在解析任务中验证。

| 入口 | 本地地址 |
| --- | --- |
| Web（Agent 根入口） | 由组合启动器打印（主端口 `http://localhost:43110/`） |
| API 健康检查 | 由组合启动器打印（主端口 `http://localhost:43111/health`） |
| Browser Service 健康检查 | `http://localhost:8001/health` |
| PostgreSQL | `localhost:15432`，以实际配置为准 |
| LiteLLM | `http://localhost:4000` |
| Temporal / UI | `localhost:7233` / `http://localhost:8233` |
| Steel | `http://localhost:3001` |

本地 Compose 的数据库、模型网关、Temporal 和 Steel 端口仅绑定回环地址，不可直接当公网部署配置。
生产拓扑在 `deploy/compose.yaml`，对宿主机只发布 Caddy 端口，仍需独立公网验收。
生产 Caddy 将 `/api/browser/sessions/*` 在同源下转发到 Browser Service 的内部 Viewer
HTML/WebSocket 路由；本地 Web 通过 `BROWSER_BASE_URL` 配置的服务端代理和 Next rewrite
复用同一路径，不能把 `8001` 或 Steel `3001/9223` 直接暴露给用户。

本地开发使用 Web `43110`、API `43111` 作为主调试端口，组合启动器会在固定的
`43110/43111`、`43120/43121` … `43180/43181` 端口池中按“成对”退避。
它先核对根目录 `.env` 与 `apps/web/.env.local` 的认证/BFF 地址，再检查两个端口；
端口占用时保留占用进程信息并选择下一对，实际 Web/API 地址注入同一批子进程，避免认证漂移。
同仓库再次执行 `dev` 会显示并复用已有实例，不另起 Next 进程。探测后发生绑定冲突时，清理
本次子进程并继续尝试下一对。现有实例的服务退出或连续三次健康检查失败时，在原端口按
1/2/4 秒退避恢复，单个服务累计最多恢复三次；编译或依赖错误、端口池耗尽会显示失败并保留日志，
不无限重启、不重放 Agent 请求。此机制不保证后台 Run 跨进程恢复。
端口池耗尽才拒绝启动，不会只替换一个服务的端口，也不会修改系统代理或终止未知进程。
统一从仓库根目录运行 `npm --prefix apps/web run dev`，然后打开启动器打印的 Web URL。
实际端口、状态和子进程 PID 写入已忽略的 `data/dev/careeract.json`，日志为 `data/dev/careeract.log`。
状态查询用 `npm --prefix apps/web run dev:status`，完整停止用 `npm --prefix apps/web run dev:stop`，
会清理启动器所属的 Web/API 子进程树。Windows 工具后台启动使用 `Start-Process -WindowStyle Hidden`，
避免服务随一次终端工具调用结束；不设置开机自启。
`npm --prefix apps/web run generate:api` 从当前 ready 实例读取实际 API 地址；smoke 脚本的
`--base-url` 同样传入 `dev:status` 显示的 Web 地址，退避后不沿用主端口。
未登录时进入注册/登录页面。生产 Web 容器内部 3000、Steel 内部 3000 是不同拓扑，保持部署配置。
`http://127.0.0.1:3001/v1/health` 是 Steel 健康接口，
不是 CareerAct Agent 页面，不能拿它代替产品页面展示。
停止本项目容器可用 `docker compose stop`；不要把删卷、全局 prune 或清空 Profile 当常规修复。

启动器会用实际绑定测试核对端口，并在 Windows 上显示占用 PID/进程；手工排查可用
`Get-NetTCPConnection -LocalPort 43110,43111,43120,43121 -State Listen`，
再按 `OwningProcess` 检查进程命令和健康；不重复启动已有开发服务，也不误停其他服务。
开发服务留在独立终端；工具后台启动时使用 `Start-Process -WindowStyle Hidden`，
将输出重定向到已忽略的 `data/dev/`，并核对 Web `/sign-in`、API `/health` 和登录后 BFF 读取；
健康接口成功不能证明认证公钥或业务链路正常。
API 通过 `uv` 的项目解释器执行 `python -m uvicorn`，避免全局/旧 `.exe` 启动器混用依赖；
reload 限定 `services/`，不因隔离检查快照或前端修改重启 API。
Web 始终用单一 `next dev`；环境变量、依赖或数据库迁移后的必要重启与普通 UI 热更新分开处理。
这不提供开机自启或 Agent Run 跨进程续跑。

## BOSS 连接请求验收

BOSS 连接请求的本地验收（不访问 BOSS、不创建浏览器会话）：

```powershell
$env:RUN_BOSS_CONNECTION_POSTGRES_TESTS = '1'
try { uv run pytest tests/api/test_boss_connections.py -q } finally { Remove-Item Env:RUN_BOSS_CONNECTION_POSTGRES_TESTS }
uv run python scripts/smoke_boss_connection.py --base-url http://localhost:43110
```

首项使用隔离 Docker PostgreSQL；次项使用当前开发 Web/API 和真实认证链路，创建两个虚构账号、
记录/撤销连接请求后退出，合成账号保留在本地开发库。退避后使用 `dev:status` 的实际 Web 地址。
连接请求的范围和后续登录门槛见[招聘沟通专题](../topics/recruiting-communication/README.md#phase-0b-产品连接请求前置增量)。

## 职业档案验收

应用 Alembic 最新迁移后，登录 CareerAct Agent 即可手动维护并确认档案。产品接口是
`GET/PUT /api/v1/profile`，浏览器只调用同源 `/api/profile`。保存携带读取时的版本，
首次创建为 null；每次成功保存生成新版本，旧版本返回 409，未确认或非法内容返回 422。
同一用例仅写一份档案，仓储在单个事务内原子执行归属过滤和版本条件更新。
所有者来自 JWT，客户端不能指定；成功及错误响应不缓存，错误不回显提交内容。

```powershell
$env:RUN_PROFILE_POSTGRES_TESTS = '1'
try { uv run pytest tests/api/test_profiles.py -q } finally { Remove-Item Env:RUN_PROFILE_POSTGRES_TESTS }
uv run python scripts/smoke_profile.py --base-url http://localhost:43110
```

第一项复用现有隔离 Docker PostgreSQL 夹具，验证迁移、真实持久化和并发；HTTP 身份签名
在测试中生成。第二项要求 Web/API 已启动且认证 URL 一致，经过真实 Better Auth/BFF/JWKS
链路，创建两个随机虚构账号并退出；账号与合成档案留在本地开发库，不发邮件、不调用模型。
脚本仅允许本地 HTTP 地址，不读取或打印用户密钥与真实档案。

页面另验收空态、编辑、确认保存、刷新恢复、保存失败保留输入、冲突后重新读取及窄屏。
草稿暂只在内存中，离开会丢失；没有历史版本浏览、上传导入或 Agent 自动修改。
调用模型前仍须单独完成只读职业上下文接入，不能从聊天可用推导 Agent 已理解档案。

## 身份与权限边界

### 材料合成实验

应用 0008 迁移后，材料 API、版本和提议可用，但默认由服务端开关关闭。
仅在本地合成验收的 API 启动进程设置 `$env:SYNTHETIC_MATERIALS_ENABLED='true'`；
正常部署保持 false。该开关不是自动脱敏或真实资料授权，P1 门槛尚未通过。
正式页面从“请伙伴创作”开始，提供合成事实后生成待审阅草稿，接受后生成 v1；
后续反馈生成绑定基准的提议，刷新恢复正文/提议/历史，旧提议不可覆盖新版本。
来源记录表示实际读取的对象版本，不能将模型表达直接当作已验证事实。

专项：设置 `$env:RUN_MATERIAL_POSTGRES_TESTS='1'` 后运行
`uv run pytest tests/api/test_materials.py -q`，结束移除该测试环境变量。
复用隔离 Docker PostgreSQL，覆盖迁移升级/回退、用户/项目隔离、重放、并发接受、
旧版本冲突和历史 Diff；不发送真实资料或进行外部投递。可见浏览器另验真实模型、
接受/拒绝/反馈、刷新恢复、保存失败保留输入与窄屏；不能以单元测试代替页面验收。

### 隐私入口验证

档案/项目写入用例与产品 JSON 入口检查明显的证件/账户长号码和凭据模式；AG-UI 在
Runtime 前检查所有提交文本，暂拒绝附件、客户端工具、任意状态/上下文。限额为 Agent
256 KiB、产品 JSON 1 MiB（项目 BFF 另限 64 KiB）。认证先于检查，认证密码/Cookie/JWT
不经职业内容检测器；不得将它们放入职业资料或聊天。错误不回显原文，不自动修改事实。

验证命令：uv run pytest tests/api/test_privacy.py tests/api/test_health.py -q。
测试仅使用合成号码/凭据和 Runtime/Repository 替身，不发送给模型。另开启档案/项目
PostgreSQL 测试验证普通内容仍能持久化。浏览器验收使用合成受限输入，检查拒绝提示及
输入修正路径，不使用真实证件或密钥。

模式检测有漏检/误报；尚不覆盖图片、任意健康/住址事实、混淆秘密或既有存量内容。关闭
Agno telemetry/debug/Tracing、媒体存储不代表会话/事件已删除；AgentOS 会开启事件存储。
不得通过启用请求正文日志或复制原始异常来诊断拒绝。材料/模型出口、浏览器观察隔离、
供应商日志、加密和各副本删除的开放条件见 [Agent 工作面门槛](../topics/workspace/DESIGN.md#隐私与数据安全前置门槛)；
未通过前不能将当前增量描述为生产隐私已闭环。

浏览器敏感执行遵循 [OpenAI Computer Use 安全指南](https://developers.openai.com/api/docs/guides/tools-computer-use-integration#handle-user-confirmation-and-consent)
的可验证原则：隔离运行环境与站点/动作白名单，页面内容不授予权限，敏感输入和对外提交在
风险点确认，执行有步数/时间/资源上限并确定性核验结果。未来的专用工具只向 Agent 暴露字段
语义、授权范围和“已填充/已核验”等非敏感状态；身份证、密码、验证码和 Cookie 明文留在
执行器或用户手中。当前 P2 尚未通过，因此不要以普通 AG-UI 文本请求模拟这一能力。

三类身份代表不同的权限边界，不要求现在建立三个账号系统或完整管理后台：

| 身份 | 归属与权限 | 当前安排 |
| --- | --- | --- |
| CareerAct 用户 | Better Auth 身份；仅操作自己的职业数据和已授权任务 | 注册得到普通用户身份，开发者自用也遵循同样约束 |
| CareerAct 平台管理员 | 未来复用 Better Auth 身份，由服务端明确授予产品管理权限 | 暂不实现角色插件或后台；不得默认首个注册者、开发者邮箱拥有管理权 |
| 框架运维管理员 | LiteLLM 等组件的独立管理凭据或管理账号 | 与产品权限分离；不通过产品注册自动创建或同步 |

同一个人可以承担用户和运维工作，但两条访问链独立。LiteLLM 管理员管理模型网关，
并不因此有权读取 CareerAct 简历、修改职业档案或代用户执行招聘操作。
用户 Session、服务推理 Key、网关管理 Key、供应商 Key 分属不同用途；
LiteLLM 虚拟 Key 不是用户登录账号，也不能代替领域数据权限检查。

### 模型网关凭据分离

API 的 Agent Runtime 使用必填的 `LITELLM_API_KEY`，缺失或为空时拒绝启动，不回退到
`LITELLM_MASTER_KEY`。Alembic 独立读取数据库配置，不再要求认证或模型凭据。
部署中 `api` 只接收推理 Key；master key 只给 LiteLLM 与一次性 `litellm-init`，
供应商 Key 只给 LiteLLM。初始化成功后才启动 API，原有 Key 策略不一致或被停用时拒绝启动。

采用固定版本 LiteLLM OSS 虚拟 Key，先供 API 服务使用；
暂不为每个产品用户创建 LiteLLM 账号，也不引入企业版、SSO 或自建权限框架。

当前原型策略由 `scripts/manage_model_key.py` 维护：仅允许 `careeract-default` 与
`careeract-openai`，仅允许 Chat Completions 与模型列表路由；每 Key 预算 5 美元、
周期参数 `30d`、30 RPM、60,000 TPM、最多 1 个在途请求。预算按网关成本估算统计，
不是供应商余额或人民币额度，也不是预付费用；周期重置时间以当前 LiteLLM 实现为准。
这些是原型的保守服务总额度，不是每位产品用户的独立额度。超限拒绝，不提供排队；
并发计数异步释放，紧接已完成请求的下一次调用也可能短暂收到 429。

### 凭据生命周期

本地在根目录执行 `uv run --no-sync python scripts/manage_model_key.py provision`，
生成或复用被忽略的 `.env.litellm`；API 自动从该文件加载服务 Key，原 `.env` 的供应商
密钥保持不变。脚本只报告状态，不输出 Key 或网关响应正文；未知结果不自动重发创建请求。
再次执行先以 Key 哈希核对网关记录，仅记录不存在时创建，不修改已有 Key 的预算和权限。
`check` 只检查策略，`revoke` 将 Key 标记为 blocked；保留停用记录，防止下次初始化重新启用。

轮换时按顺序操作：

1. `uv run --no-sync python scripts/manage_model_key.py provision --key-file .env.litellm.next`。
2. 保留旧文件为 `.env.litellm.previous`，将新文件切换为 `.env.litellm`，重启 API，验证模型调用。
   若使用环境变量或 Compose，需要同步其来源；环境变量优先于 dotenv 文件。
3. 确认新链路正常后，执行 `uv run --no-sync python scripts/manage_model_key.py revoke --key-file .env.litellm.previous`。
   被停用的旧 Key 不应再次用于启动；异常时保留文件与状态以便对账，不反复生成新 Key。

已有试用流量时需要单独安排轮换窗口。撤销阻止后续调用，不承诺中断已经进入供应商的请求。
轮换策略变更需先核对影响；不通过删除旧记录再重建同一 Key 来清零预算或恢复已撤销权限。

部署准备（只描述流程，不代表已获购买或公网部署授权）：

```powershell
uv run --no-sync python scripts/manage_model_key.py prepare --key-file deploy/.env.litellm
docker compose --env-file deploy/.env --env-file deploy/.env.litellm -f deploy/compose.yaml up -d --build --wait
```

`deploy/.env` 根据部署示例另行配置；`prepare` 仅准备随机服务 Key，随后内网一次性
`litellm-init` 负责注册和核对。文件必须留在受控主机并限制读取权限；不将环境文件、
`docker inspect` 的完整环境或展开后的 Compose 配置粘贴到日志。生产运维不开放 LiteLLM 公网端口。

### 模型权限验收

```powershell
$env:RUN_MODEL_GATEWAY_TESTS = '1'
try { uv run pytest tests/api/test_model_gateway.py -q } finally { Remove-Item Env:RUN_MODEL_GATEWAY_TESTS }
```

测试创建独立 LiteLLM OSS 与 tmpfs PostgreSQL、临时网络和回环端口，结束清理；
使用虚构凭据与模型替身，不加载本地供应商 Key、不产生模型费用。
覆盖允许模型、SSE、越权模型、管理路由拒绝、预算/RPM/TPM、重复初始化和轮换停用。
为等待 LiteLLM 异步释放在途计数，正常模型探测之间间隔 1 秒；不是生产请求重试策略。
真实供应商与 BFF SSE 另行验证，不能用替身测试声称真实模型可用。

持续保留的验收要求：

1. API 改用独立推理凭据，缺失时明确报错，不回退到 master key；迁移进程不接收模型凭据。
   master key 仅供网关与受控运维流程使用，供应商 Key 仅供网关使用，均不下发给浏览器。
2. 在固定镜像的隔离环境实测：允许模型可调用，未授权模型及管理操作被拒绝；
   覆盖创建/修改/删除 Key 和管理配置等相关路由，不能仅凭 OpenAPI 字段认定限制生效。
   先用可控模型替身验证权限，再验证真实供应商与 BFF 流式链路，分别报告结果。
3. 提供可重复的凭据初始化、轮换和撤销流程；秘密只写入忽略文件或运行环境，
   不输出响应中的 Key，不覆盖已有供应商密钥；新旧部署与冒烟配置同步调整。
4. 核对当前 OSS 版本的模型范围、预算和限流能力并实测生效；预算检查不等于绝对费用上限。
   对外试用前确定并验证额度、并发限制及停用方式；服务总额度不冒充产品用户独立配额。
5. 运维入口仅本机或受控内网可达，公网只开放产品入口；同步检查 LiteLLM、Temporal、
   AgentOS 管理接口和 Steel/CDP 的路由边界，不能因 Next.js 登录成功就认定底层接口受保护。

### 随业务落地与后续阶段

- 第一条职业档案纵切片同时实现所有权校验：用户 ID 来自已验证身份，查询、修改和删除
  都限定归属；用两个真实测试用户验证列表、直接资源 ID 和写入无法跨用户访问。
  后续材料、Agent Session、任务、对象存储和浏览器能力按接入顺序做同样验收。
- 平台管理后台在出现明确的用户停用、额度配置等用例后再实现，沿用 Better Auth 身份，
  通过受控流程授予权限并记录管理动作；届时需要 Schema 变更时新增 Alembic revision。
  暂不预建组织、多租户角色矩阵、收费或账号联邦。
- 云厂商控制台管理云资源、网络、账单和部署；Serverless 可减少部分运维，不能自动提供
  CareerAct 用户停用、业务额度或任务处理界面。原型使用现有框架控制台与受控脚本即可，
  有重复的产品运营需求后再决定是否需要专门管理页面。
- 浏览器安全集成继续按[开放前检查](#浏览器开放前检查)推进；对外启用浏览器能力前
  必须完成相应隔离与接管验收。它不阻塞不使用浏览器的职业档案开发，未通过的控制入口保持关闭。

## 镜像与浏览器底座验收

在根目录构建三个服务镜像，不需要把供应商密钥传入构建器：

```powershell
docker build -f services/api/Dockerfile -t careeract-api:local .
docker build -f services/browser/Dockerfile -t careeract-browser:local .
docker build -f services/worker/Dockerfile -t careeract-worker:local .
docker run --rm careeract-worker:local /app/.venv/bin/python -c "import torch; assert torch.version.cuda is None; import cv2; from docling.document_converter import DocumentConverter; print('CPU dependencies OK')"
docker compose up -d --wait steel
uv run --no-sync python scripts/smoke_steel.py
```

Worker 的 Torch / Torchvision 从官方 CPU 索引解析并由 `uv.lock` 锁定，避免普通 Linux
服务器下载 CUDA 依赖；Worker 镜像包含 OpenCV 必需的系统库。导入成功不证明 Docling
模型资源已下载、中文文档解析或离线解析已通过。

Steel 冒烟脚本仅创建内存中的虚构表单，验证会话、CDP 填写/点击/读取、Viewer HTML 和释放。
已有 live 会话时拒绝运行，防止打断人工操作；不要与其他浏览器执行器并行运行。
加 `--viewer-channel msedge` 可用已安装的 Edge 开启独立无登录 headless 浏览器，验证
Viewer 画面、鼠标点击、普通键盘输入及远端表单结果；不读取用户浏览器 Profile。
该参数是可重复的自动检查工具；交互开发和页面验收按当前协作约定使用可见 Computer Use，
让用户能看到页面和操作，不以后台 headless 操作代替可见验收。
该模式使用 1920×900 的观察窗口。当前上游 Viewer 在较窄窗口下可能裁切画面，且
`Ctrl+A` 转发实测不符合全选预期，不能据此宣称完整接管体验通过。
它不验证 CareerAct 同源授权代理、租约隔离、browser-use 智能执行或招聘站点可用性。
Steel/CDP 开发端口只绑定本机回环地址。CDP 发现请求使用 localhost Host，并把发现的
WebSocket 地址映射回实际连接端口，兼容当前 Steel Nginx 转发与 Chromium Host 校验。
开发 Compose 的 `DOMAIN=127.0.0.1:3001` 用于生成本地 Viewer WebSocket 地址；
该值不可直接用于生产，生产需通过 CareerAct 同源授权代理访问。

容器网络复测（独立执行，结束删除临时容器）：

```powershell
docker run -d --name careeract-browser-smoke --network careeract-dev_default -e STEEL_BASE_URL=http://steel:3000 -e ANONYMIZED_TELEMETRY=false -e BROWSER_USE_CLOUD_SYNC=false careeract-browser:local
docker cp scripts/smoke_steel.py careeract-browser-smoke:/tmp/smoke_steel.py
docker exec careeract-browser-smoke /app/.venv/bin/python /tmp/smoke_steel.py --api-url http://steel:3000 --cdp-url http://steel:9223
docker rm -f careeract-browser-smoke
```

## Docling 材料解析验收

`scripts/smoke_docling.py` 在 Linux Worker 镜像内生成虚构中文 DOCX 和英文文本 PDF，
验证解析成功及关键文本，CPU 单任务运行。默认关闭 OCR 和表格识别，只下载 PDF 布局模型；
不据此声称扫描件、中文 PDF、复杂表格或真实简历结构准确率已经通过。

在 PowerShell 执行（使用独立容器；`data/` 已忽略）：

```powershell
New-Item -ItemType Directory -Force data/docling-smoke | Out-Null
docker create --name careeract-docling-smoke --mount "type=bind,source=$((Resolve-Path data/docling-smoke).Path),target=/data" --entrypoint /app/.venv/bin/python careeract-worker:local /tmp/smoke_docling.py
docker cp scripts/smoke_docling.py careeract-docling-smoke:/tmp/smoke_docling.py
docker start -a careeract-docling-smoke
docker inspect --format '{{.State.ExitCode}}' careeract-docling-smoke
docker rm careeract-docling-smoke
```

首次运行需访问 Hugging Face 下载公开模型；缓存保存在 `data/docling-smoke/models`，
不读取真实简历或模型供应商密钥。确认退出码为 0 后，使用同样缓存做断网验收：

```powershell
docker create --name careeract-docling-offline --network none --mount "type=bind,source=$((Resolve-Path data/docling-smoke).Path),target=/data" --entrypoint /app/.venv/bin/python careeract-worker:local /tmp/smoke_docling.py --offline
docker cp scripts/smoke_docling.py careeract-docling-offline:/tmp/smoke_docling.py
docker start -a careeract-docling-offline
docker inspect --format '{{.State.ExitCode}}' careeract-docling-offline
docker rm careeract-docling-offline
```

`--offline` 禁用 Hub 网络请求，`--network none` 进一步验证容器完全断网仍可解析。
正式解析 Activity 尚未实现，当前生产 Worker 也尚未挂载此缓存；部署前需将已验证的模型资源
预置到受控存储/镜像并固定版本，不能依赖服务器首次处理材料时临时从国外下载。
脚本报告的峰值 RSS 是单个 Python 进程的 Linux 统计，不是整机/容器栈峰值。

## Temporal 恢复验收

```powershell
uv run --no-sync python -m scripts.smoke_temporal
```

脚本复用 Compose 中固定的 Temporal 镜像，创建独立临时容器、动态回环端口、临时数据库
目录和独立测试队列，不重启现有开发容器。诊断 Workflow 不注册到产品 Worker。
它验证等待状态在 Worker 强制终止后重放、Worker 离线时信号被接受、Temporal 强制
终止后同一个 Run 完成，以及取消和执行超时的原生终态。重启后重新获取 Docker 动态端口。
正常结束或断言失败都会清理测试进程、容器和临时目录；整个命令被外部强制终止时可能需
按本轮创建的 `careeract-recovery-*` 名称人工清理，不要批量删除其他容器或卷。

这证明的是本地 SQLite Dev Server 和 Temporal SDK 的恢复链路，未验证生产 PostgreSQL
Temporal 拓扑、Activity 副作用重试、浏览器恢复、业务状态回写或产品级状态机。

## 完整容器拓扑验收（本地隔离）

先构建前述三个 Python 镜像，再执行下面命令。需支持 `!override` 的 Docker Compose
2.24.4 或更新版本。该覆盖文件复用生产拓扑，仅替换应用镜像标签和公网端口映射。

```powershell
docker build -t careeract-web:local apps/web
uv run --no-sync python scripts/smoke_stack.py prepare
docker compose -p careeract-smoke --env-file data/stack-smoke.env -f deploy/compose.yaml -f deploy/compose.smoke.yaml up -d --no-build --wait
uv run --no-sync python scripts/smoke_stack.py check --restart
docker compose -p careeract-smoke --env-file data/stack-smoke.env -f deploy/compose.yaml -f deploy/compose.smoke.yaml down
```

入口仅为 `http://localhost:18080`。脚本首次生成独立随机凭据到被忽略的
`data/stack-smoke.env`，已有文件不覆盖，不读取根 `.env`，不填入供应商密钥。
旧版本文件缺少服务 Key 时只追加该项，不重写已有凭据。`litellm-init` 自动注册服务 Key；
验收还检查 API 不含管理/供应商凭据、迁移无需模型凭据及重复初始化成功。
不要删除配置后直接复用旧数据库卷，否则随机密码会与旧数据库不一致。
`down` 保留本项目测试卷；不要使用全局 prune 或把开发数据库接入这个测试项目。

验收覆盖：Caddy → standalone Web → Better Auth/PostgreSQL → JWT/JWKS → FastAPI；
匿名和错误 Origin 拒绝；退出登录后拒绝；可选 Web/API 重启后 Session 与 JWKS 保持；
正式 Temporal Server/PostgreSQL 与 Worker 执行；Browser/Steel/LiteLLM 内网健康接口。
BFF 使用缺少必需字段的请求，期待通过认证后得到 API 的 422；不调用模型、不产生模型费用。
每次执行创建虚构测试账号，数据仅留在独立测试库。本地 HTTP 不替代域名、TLS、备案或云端验收。

Web 镜像使用固定 Node digest；构建只用固定占位配置，不支持把真实认证凭据传为 build args。
正式运行配置仍由 Compose 环境变量注入。Temporal 动态配置文件必须挂载，默认 `{}` 使用
服务默认参数。`up --wait` 中没有显式健康检查的服务仍可能只代表进程已启动，以脚本结果为准。

单独检查正式 Temporal/Worker 可执行 `uv run --no-sync python scripts/smoke_stack.py temporal`。
该检查最多进行 12 次只读任务队列探测，要求队列可读取且存在 Workflow poller，
每次连接/命令限时 2s/3s，失败间隔 2s；
Docker 子进程另有限时 60s。就绪后只提交一次独立 ID 的健康 Workflow，执行限时 30s，
失败立即报告，不自动重发 Workflow。就绪重试会打印次数，不能用重试成功掩盖首次失败。

## 浏览器持久租约与服务凭证验收

普通 `uv run pytest` 运行签名验证及进程内规则测试，跳过需要 Docker 的数据库测试。
执行真实 PostgreSQL 验收：

```powershell
$env:RUN_BROWSER_POSTGRES_TESTS = '1'
try { uv run pytest tests/browser -q } finally { Remove-Item Env:RUN_BROWSER_POSTGRES_TESTS }
```

测试创建独立 `careeract-lease-test-*` 容器，复用固定 PostgreSQL 镜像，使用 tmpfs 数据库
和动态回环端口；结束删除该测试容器。使用无秘密的临时数据库和内存生成的签名密钥，
迁移在临时工作目录运行，不加载仓库 `.env`。本地 trust 认证仅用于此隔离测试实例，
不适用于开发或生产库。外部强制终止测试后可按具体名称清理遗留测试容器。

覆盖旧 Schema 升级、回退及重新升级时认证数据保留，两个独立进程争抢，
进程退出后的租约保持，HTTP 签名/范围检查、防重放、撤销和过期后的保守交接。
部分 HTTP 测试通过 ASGITransport 直连实际应用与 PostgreSQL；另有测试启动独立
Uvicorn Browser 子进程，由真实 API 签名/HTTP 适配器经回环 TCP 访问。均未经过 Caddy。
子进程仅接收临时公钥，签名私钥保留在测试进程内存，不生成真实业务密钥。

服务默认只提供健康检查，内部控制操作返回 503。实验性启用需要同时配置：

- `BROWSER_DATABASE_URL`：SQLAlchemy 的 `postgresql+asyncpg` URL，指向已迁移数据库。
- `BROWSER_COMMAND_PUBLIC_KEY_FILE`：容器内 Ed25519 PEM 公钥文件路径，只用于 API 命令验证。
- API 的 `BROWSER_BASE_URL` 与 `BROWSER_COMMAND_PRIVATE_KEY_FILE` 配置内部控制客户端；
  后者是独立 Ed25519 PEM 私钥，不是 Better Auth 密钥。只有 URL 而没有私钥时拒绝启动。
  未配置 URL 时保持产品物理会话控制关闭。Browser Service 配置上述数据库/公钥后会复用
  `STEEL_BASE_URL` 装配专用内部创建/释放路由；Web 登录仍须经过产品登录任务和 Viewer 授权。

API 私钥不放在 Browser，密钥不得复用用户登录或模型供应商密钥。
当前 Compose 不自动开启控制入口。API 已有登录任务授权、签名注册/创建/释放和同源
Viewer HTML 代理；产品仍要求独立的 Browser Service 配置、可见登录核验和真实站点只读复验，
不能把合成创建证据当成已登录。
开放条件见[浏览器开放前检查](#浏览器开放前检查)。真实执行器已有下述隔离测试，尚不支持产品级浏览器执行或人工接管。

### 浏览器开放前检查

以下检查未通过时保持产品控制入口关闭，不阻塞档案等不使用浏览器的功能；当前实现和
已验证证据见 STATUS，租约规则见 [Sessions](../../services/browser/sessions/README.md)。

- 服务端按 Session、任务、会话归属和授权记录签发短时凭证；不能信任请求正文的 user_id。
  验证跨用户、范围错误、过期凭证、撤销、两个进程竞争及重启后的保守恢复。
- 停止新动作、等待在途操作结束、关闭旧连接且阻止其重连后才交接。租约过期、同用户身份或
  旧页面对象失效不能证明单写入；重启不能将存活 Steel 会话当成空闲，结果未知不自动重试。
- 同源 Viewer 在 WebSocket 升级时校验 Origin、Session 和会话所有权，撤销后关闭已有通道。
  先验证 Caddy/Next.js 的转发路径，不假设普通 Route Handler 能处理升级；不暴露原始 CDP URL。
- 在可见虚构页面验证 Agent → 人工 → Agent 互斥、跨用户拒绝、撤销断连、刷新与退出；
  独立检查窄窗口、快捷键和中文输入。不把后台集成通过写成人工接管已完成。

## 执行器断连验收

Steel 生命周期适配器的故障/并发/重建检查使用隔离 PostgreSQL 和合成 HTTP 替身：

```powershell
$env:RUN_BROWSER_POSTGRES_TESTS = '1'
try { uv run pytest tests/browser/test_steel_sessions.py -q } finally {
    Remove-Item Env:RUN_BROWSER_POSTGRES_TESTS
}
```

额外设置 `RUN_STEEL_SESSION_TEST=1` 会对已启动的本地固定 Steel 镜像执行一项真实
创建/只读核对/释放检查；结束后移除该环境变量。有活动会话会拒绝创建，不能因此释放
他人会话。只使用合成新会话，不访问招聘站点。0018 迁移在隔离测试库升级/回退，
不修改日常库；真实调用必须先应用迁移。此入口不验证 Profile 隔离或产品人工登录。
不确定占用保留等待核对；不能删除占用记录来恢复运行，规则见
[Steel 生命周期](../../services/browser/sessions/README.md#steel-lifecycle-adapter)。

固定 Steel 实例的 Profile canary 使用两个不同路径、两个顺序会话和 `example.com` 的
合成 localStorage 标记，不读取招聘页面：

```powershell
uv run python scripts/smoke_steel_profile.py
```

它只证明新会话没有继承前一会话的网页存储；不证明登录态可持久化，也不验证真实 Profile
目录是否按路径保存。失败、超时或释放结果不明时保留会话并人工核对，不自动重试。

验证固定 Steel 的原生 context 导出/导入，可执行合成 Cookie/localStorage 三会话 canary：

```powershell
uv run python -m scripts.smoke_steel_context
```

先确认没有活动产品会话；脚本遇到 live 会话会拒绝操作。导出只选取本次随机合成标记，按明确的
`https://example.com` origin 恢复到第二个会话，并验证第三个空会话不继承标记。context 只在内存中，
不打印或存文件；当前 Steel 的导出域名键与恢复 origin 键不同，适配依据见招聘沟通专题。
此实验不是加密持久化、磁盘 Profile 隔离或真实账号恢复验收；创建/释放结果不明时不重试。

加密 context 的内部适配检查使用隔离 PostgreSQL；开启第二个开关才运行固定 Steel 的
真实合成保存/恢复/空会话 canary：

```powershell
$env:RUN_BROWSER_POSTGRES_TESTS = '1'
$env:RUN_STEEL_PROFILE_TEST = '1'
try {
    uv run pytest tests/browser/test_browser_context.py tests/browser/test_browser_profiles.py tests/browser/test_steel_context.py -q
} finally {
    Remove-Item Env:RUN_BROWSER_POSTGRES_TESTS
    Remove-Item Env:RUN_STEEL_PROFILE_TEST
}
```

同样拒绝已有活动 Steel 会话，只使用 `example.com` 合成 Cookie/localStorage；密钥仅在测试内存中，
迁移 0019 仅应用隔离库。正式适配读取 Playwright 的实时 canonical origin，避免 Steel 原生导出
混入磁盘旧值；恢复复用 Steel 原生 `sessionContext`。支持范围、撤销含义和尚未装配的生产密钥见
[加密 context 边界](../../services/browser/sessions/README.md#encrypted-context-snapshots)。
该入口不证明真实 BOSS 登录、浏览器进程重启恢复或磁盘 Profile 清理；不自动重试不确定操作。

登录执行对象和 Browser Service 注册/撤销的内部链路检查：

```powershell
$env:RUN_BROWSER_POSTGRES_TESTS = '1'
try { uv run pytest tests/api/test_execution_semantics.py -q } finally {
    Remove-Item Env:RUN_BROWSER_POSTGRES_TESTS
}
```

该入口创建隔离 PostgreSQL 并升级/回退至 0020；实际校验签名和 Browser Service ASGI 路由，
丢失响应/拒绝/取消为故障替身，不访问 Steel 或招聘平台。日常库不会随测试迁移；装配产品前须先升级。

签名物理会话路由及领域创建证据检查：

```powershell
$env:RUN_BROWSER_POSTGRES_TESTS = '1'
$env:RUN_STEEL_SESSION_TEST = '1'
try {
    uv run pytest tests/browser/test_signed_lifecycle.py tests/api/test_execution_semantics.py tests/api/test_browser_control.py -q
} finally {
    Remove-Item Env:RUN_BROWSER_POSTGRES_TESTS
    Remove-Item Env:RUN_STEEL_SESSION_TEST
}
```

第二个开关仅增加一项固定 Steel 的真实创建/释放，不打开 BOSS。存在活动会话时拒绝干扰；
其余检查使用隔离 PostgreSQL/ASGI 与合成 Steel 故障响应。0021 迁移不应用日常库，
尚未验证产品 HTTP、同源 Viewer 或人工登录。
登录授权最长 15 分钟，同键重放不会续期；内部注册只建立会话归属记录，不代表浏览器已启动或已登录。
未知/中断尝试不能重发，撤销后仍须核对浏览器断连和 Profile 清理。具体范围见招聘沟通专题。

生命周期规则测试：`uv run pytest tests/browser/test_executor_lifecycle.py -q`。
真实 Steel/Playwright/PostgreSQL 联合检查：先启动本地 Steel，然后执行：

```powershell
$env:RUN_BROWSER_POSTGRES_TESTS = '1'
$env:RUN_STEEL_EXECUTOR_TEST = '1'
try { uv run pytest tests/browser/test_steel_executor.py -q -s } finally {
    Remove-Item Env:RUN_BROWSER_POSTGRES_TESTS
    Remove-Item Env:RUN_STEEL_EXECUTOR_TEST
}
```

测试遇到已有 live Steel 会话会拒绝继续，仅操作新建的虚构内存表单；独立 PostgreSQL
容器和所建 Steel 会话在结束时清理。验收停止、旧 CDP 连接断开、旧页面对象写入失败，
并重新连接核对页面结果仍在。该模式是后台服务集成测试，不代表可见 UI 或人工接管验收。

可见验收需另设 `RUN_VISIBLE_EXECUTOR_TEST=1`。测试会输出被忽略的 `data/executor-*`
目录，其中 `viewer.txt` 是本次本地观察地址。先在可见浏览器打开地址，再创建该目录的
`start` 空文件启动后台动作。看到 `VISIBLE_INPUT` 后，在 Viewer 输入框末尾追加
` Human verified` 并点击 `Save locally`；关闭 Viewer 标签后创建 `viewer-closed` 空文件。
每个等待最多 300s，超时会报告失败并清理。此模式使用原始本地 Viewer，未证明身份隔离。
工具不能操作可见浏览器时报告未验收，继续独立后台检查，不把两者互相替代。

## 凭据拦截

首次克隆安装 Gitleaks 8.30.1（Windows 可用 `winget install --id Gitleaks.Gitleaks -e`），
然后在仓库根目录执行 `git config --local core.hooksPath .githooks`。
本机还需安装 uv 并完成前面的依赖同步。Git 不会自动启用克隆仓库中的 hooks。

每次 commit 都扫描暂存区；真实 `.env` 文件即使被强制暂存也会被阻止，`.env.example`
允许提交但仍扫描内容。Gitleaks 缺失或扫描失败会阻止提交，输出启用完整脱敏。
手动检查：`uv run --no-sync python scripts/check_secrets.py`；历史检查加 `--history`。
尚未暂存的收尾检查加 `--worktree`，扫描相对 HEAD 的修改与非忽略新文件的完整内容，
在临时快照中扫描后自动清理；不扫描被忽略的私人资料，也不改变真实暂存区。
CI 的 Secrets 工作流扫描全部 Git 历史，不需要供应商密钥，也不读取本地环境文件。
本地 hook 可以被绕过；远程需将 `secrets` 检查设为分支保护必需项才会阻止合并。
检测有覆盖边界，不能代替审查；发现误报须精确核实，不整体跳过 vendor 或测试文件。
`.gitleaksignore` 仅记录已核对的上游快照指纹：测试值、截断示例、公开标识和代码误报。
新提交或不同位置的匹配不继承这些例外。禁止未经核对批量刷新例外。

## 检查范围

| 改动 | 最小有效验收 |
| --- | --- |
| 文档、指令、Skill | 链接/路径、触发范围、冲突、格式、Git 忽略边界 |
| Python 规则或修复 | 相关 Ruff/mypy/pytest；修复应覆盖原失败行为，而非复制实现写断言 |
| API、认证、迁移 | 相关测试；真实数据库或会话集成；用户隔离、无效凭据、旧 Schema 升级 |
| Worker、浏览器 | 相关测试与可控集成；重复执行、等待/取消、恢复、结果不明时的处理 |
| UI 行为 | lint/typecheck，必要时 build；运行页面检查加载、空态、错误和关键交互 |

### 提交与变更门槛

`pre-commit` 先执行 `check_changes.py` 的暂存区空白检查，再运行 Gitleaks；
`commit-msg` 与 CI 使用同一脚本核对提交主题和保护路径。首次克隆沿用 `.githooks` 设置；
新 hook 作为可执行脚本提交（Git mode 100755），不安装 Husky 或 commitlint。

本地 commit 自动执行的只有上述空白、秘密、提交主题和保护路径检查；不会自动运行
Ruff、mypy、pytest 或 Web lint/typecheck/test/build。Agent 须在提交前按根 AGENTS 主动完成
适用的完整检查；CI 是另外一次执行。拆分提交须核对每批新增文件和导入依赖，不能依赖
后续未提交文件才通过；必要时从暂存树导出隔离快照验证。

依据：[Git hooks](https://git-scm.com/docs/githooks) 规定 hooksPath 与可执行位；
[React Effect 数据读取](https://react.dev/reference/react/useEffect#fetching-data-with-effects)
说明响应乱序与清理保护；Next 客户端边界以已安装版本的 `use-client` 指南为准。
提交主题和按职责拆分属于本项目约定，不声称是框架强制要求。

主题使用 `<type>(<scope>): <具体结果>`，type 为 feat/fix/refactor/perf/test/docs/chore/build/ci/revert，
scope 为小写领域名；禁止仅写 update、修复问题、继续推进。历史主题只诊断，不改写。
CI 检查本次新增的非 merge 提交，不追溯强制整改全部旧历史。

`vendor/` 与生成类型不能混入产品提交；确认需改时单独使用 `chore(vendor): ...`、
`chore(generated): ...` 或 `build(generated): ...`，且该提交只包含对应保护组。
自动检查只能识别路径和提交隔离；vendor 上游缺陷证据、生成命令/来源仍需人工审查。
`node_modules/` 与 `.next/` 始终拒绝。普通依赖版本升级继续通过清单和锁文件管理。

```powershell
uv run python scripts/check_changes.py --worktree
uv run python scripts/check_changes.py --range "<base>..HEAD"
uv run ruff format --check services tests scripts/check_changes.py scripts/check_secrets.py
uv run ruff check services tests scripts/check_changes.py scripts/check_secrets.py
uv run mypy services tests scripts/check_changes.py scripts/check_secrets.py
npm --prefix apps/web run test
```

前端回归使用 Node 内置 test 和已安装 TypeScript 编译实际源码；BFF 认证/上游使用显式替身，
不验证 Next 路由运行时或完整 React DOM。真实页面、认证与数据库验证分别报告。
CI 运行这些检查及已有 Web lint/typecheck/build、pytest、Secrets；本地执行通过不代表远程 CI 已运行。

代码提交前的完整命令在根 AGENTS 中维护，不在此复制。涉及跨层依赖时运行架构边界测试。
纯文案/样式无需新增形式化测试；模型和站点行为不能只靠 mock 或页面截图推导业务正确性。

验收报告给出命令/场景、结果与限制；UI 同时说明是否实际操作。真实外部写入需要具体授权，
先用测试页面或无副作用读取验证；结果不明时进入对账，不自动重试真实提交。
可在被忽略的 `data/` 留本地诊断，公开证据必须脱敏。

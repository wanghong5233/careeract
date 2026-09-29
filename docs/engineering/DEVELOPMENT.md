# 本地开发与验证

## 先找对信息

- 当前范围与下一步：[STATUS](STATUS.md)。稳定架构规则与代码检查命令：[AGENTS](../../AGENTS.md)。
- Web：[前端指令](../../apps/web/AGENTS.md)；API：[REST 约定](../../services/api/routes/README.md)。
- 任务：[Workflow 边界](../../services/worker/workflows/README.md)；浏览器：[服务边界](../../services/browser/README.md)。
- 专项流程：[Skills 说明](SKILLS.md)。PRD、详细架构和历史采购材料可能仅在所有者本地存在。

## 单人开发流程

1. 开工先检查工作区与 STATUS，只选择一个用户可感知的交付目标，明确范围、不做什么和
   验收条件。新业务开始前先收尾已有改动，避免不同目的长期混在工作区。
2. 常规顺序开发沿当前主线进行；大范围重构、不确定实验、并行工作或需要独立修复线上问题时，
   使用短期分支，必要时用 worktree 隔离。无需固定 develop 分支、逐任务 PR 或审批仪式。
3. 按页面、接口、领域规则和持久化组成的完整路径推进。跨服务且需要跨会话的复杂任务在
   `plans/` 维护一份执行计划并从 STATUS 链接，其他任务直接使用 STATUS 的下一步。
4. 开发中运行最小相关检查，交互功能使用可见浏览器验收；完成条件包括成功路径、错误反馈、
   持久化和用户隔离。自动检查、真实集成与人工页面操作分别记录，不互相替代。
5. 提交按目的划分，允许一个交付目标包含多个可独立检查的提交，不按文件数或对话轮次拆分。
   提交前审查最终差异，执行根 AGENTS 规定的检查，通过暂存区凭据扫描；未经用户授权不提交。
   涉及迁移时另行确认兼容和数据保留，Git 回退不等于数据库回退。
6. 收尾更新 STATUS 的结果、限制和下一步。缺陷沉淀为有效回归测试，重复操作沉淀为脚本或
   本指南，稳定约束放 AGENTS 或服务 README；多次复用的专业判断流程才考虑新增 Skill。
   计划完成后按根 AGENTS 的文档规则回收结论，不持续堆积每轮开发报告。

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

3. 先启动模型网关并初始化受限服务 Key，再分别在独立终端启动 Web 与 API：

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
   uv run --package careeract-api uvicorn services.api.app.main:app --reload
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
| Web | `http://localhost:3000` |
| API 健康检查 | `http://localhost:8000/health` |
| Browser Service 健康检查 | `http://localhost:8001/health` |
| PostgreSQL | `localhost:15432`，以实际配置为准 |
| LiteLLM | `http://localhost:4000` |
| Temporal / UI | `localhost:7233` / `http://localhost:8233` |
| Steel | `http://localhost:3001` |

本地 Compose 的数据库、模型网关、Temporal 和 Steel 端口仅绑定回环地址，不可直接当公网部署配置。
生产拓扑在 `deploy/compose.yaml`，对宿主机只发布 Caddy 端口，仍需独立公网验收。

如果 3000 已被系统占用，不终止系统进程。可临时用 3100，分别在两个终端启动，
只覆盖当前进程环境，保留已有凭据文件：

```powershell
$env:BETTER_AUTH_URL = 'http://localhost:3100'
$env:API_BASE_URL = 'http://127.0.0.1:8000'
npm --prefix apps/web run dev -- --hostname 127.0.0.1 --port 3100
```

```powershell
$env:AUTH_ISSUER = 'http://localhost:3100'
$env:AUTH_AUDIENCE = 'http://localhost:3100'
$env:AUTH_JWKS_URL = 'http://127.0.0.1:3100/api/auth/jwks'
uv run --package careeract-api uvicorn services.api.app.main:app --host 127.0.0.1 --port 8000
```

打开 `http://localhost:3100`，未登录时进入注册/登录页面。变更端口必须同步认证地址，
不要只改 Next.js 监听端口。`http://127.0.0.1:3001/v1/health` 是 Steel 健康接口，
不是 CareerAct 工作台，不能拿它代替产品页面展示。
停止本项目容器可用 `docker compose stop`；不要把删卷、全局 prune 或清空 Profile 当常规修复。

## 身份与权限边界

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
- 浏览器安全集成继续按[专项计划](plans/BROWSER_SAFETY_PLAN.md)推进；对外启用浏览器能力前
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

API 私钥不放在 Browser，密钥不得复用用户登录或模型供应商密钥。
当前 Compose 不自动开启控制入口。API 内部已有签名/HTTP 适配器，但尚无产品级
授权校验、签发、注册或撤销用例，不可直接把用户请求转换成可信控制上下文。
详见[安全集成计划](plans/BROWSER_SAFETY_PLAN.md)。真实执行器已有下述隔离测试，尚不支持产品级浏览器执行或人工接管。

## 执行器断连验收

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

代码提交前的完整命令在根 AGENTS 中维护，不在此复制。涉及跨层依赖时运行架构边界测试。
纯文案/样式无需新增形式化测试；模型和站点行为不能只靠 mock 或页面截图推导业务正确性。

验收报告给出命令/场景、结果与限制；UI 同时说明是否实际操作。真实外部写入需要具体授权，
先用测试页面或无副作用读取验证；结果不明时进入对账，不自动重试真实提交。
可在被忽略的 `data/` 留本地诊断，公开证据必须脱敏。

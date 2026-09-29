# 本地开发与验证

## 先找对信息

- 当前范围与下一步：[STATUS](STATUS.md)。稳定架构规则与代码检查命令：[AGENTS](../AGENTS.md)。
- Web：[前端指令](../apps/web/AGENTS.md)；API：[REST 约定](../services/api/routes/README.md)。
- 任务：[Workflow 边界](../services/worker/workflows/README.md)；浏览器：[服务边界](../services/browser/README.md)。
- 专项流程：[Skills 说明](SKILLS.md)。PRD、详细架构和历史采购材料可能仅在所有者本地存在。

## 环境

下面使用仓库根目录下的 PowerShell。Python/Node/uv 的 CI 基准看
[ci.yml](../.github/workflows/ci.yml)，依赖版本以 `uv.lock` 和 `apps/web/package-lock.json` 为准。
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

3. 分别在独立终端启动 Web 与 API：

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

本地 Compose 暴露开发端口，不可直接当公网部署配置。生产拓扑在 `deploy/compose.yaml`，仍需独立验收。
停止本项目容器可用 `docker compose stop`；不要把删卷、全局 prune 或清空 Profile 当常规修复。

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

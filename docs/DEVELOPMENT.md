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

   LiteLLM 还需要真实 provider/model 映射与可用密钥；`careeract-default` 只是别名，容器启动不能证明模型可调用。
   `.env` 设置不会自动补齐缺少的 provider 配置。Docling 的模型下载、离线资源与中文字体也需在解析任务中验证。

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

## 按改动选择验收

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

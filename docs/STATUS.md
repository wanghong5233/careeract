# CareerAct 当前状态

更新：2026-09-28。此文件是当前阶段与交接入口；代码和实际运行证据决定已实现状态。

## 目标与范围

CareerAct 是面向个人的职业 Agent Web 工作台，围绕档案、材料版本、岗位、申请、任务和结果组织。
首要目标是开发者自用、可复现且可展示的工程代表作，随后通过少量真实试用改善产品。
采用渐进开发节奏，不承诺短假期内完成公开商业化；Star 和用户规模不是首次发布的门槛。

近期顺序：开发协作初始化 → 本地关键集成验证 → 一条用户在场的求职闭环 → 小范围体验。
长期保留 BOSS、猎聘、企业 ATS、后台任务和授权托管方向，不把全部长期范围当成本次任务。
模拟面试、收费、规模化推广、客户端扩展和多种浏览器执行后端暂不展开。

本地通过后再讨论短期云端验证；不预购季度服务器，不默认部署或购买硬件。
云端浏览器适合零安装与设备离线后的执行；本地开发时同一服务可运行在开发机。

## 当前证据

| 项目 | 已知事实 | 不能据此声称 |
| --- | --- | --- |
| 仓库 | 前后端、API、Worker、Browser 和 vendor 骨架存在 | 完整产品可用 |
| 身份与协议 | PostgreSQL 迁移、真实注册/Session、JWKS、BFF 鉴权、API 入口和 Agent SSE 已在本机通过 | 生产认证配置已通过 |
| 业务 | 领域边界、端口和规则已有定义，核心求职业务尚未完成 | 已能可靠填表、投递、值班 |
| 部署 | 四个应用镜像和生产拓扑的本地隔离链路通过；Temporal 本地等待恢复、取消、超时和 Steel 基础输入通道通过 | 公网部署、业务任务恢复、完整人工接管或求职业务已通过 |
| 检查 | 冻结依赖同步、Ruff 格式/检查、mypy、17 个 pytest 已通过；此前 Web lint/typecheck/build 已通过 | 真实招聘站点验收或生产部署通过 |
| 开发硬件 | 32GB 内存、Ultra 7 155H，具备起步条件 | 整套服务峰值占用已经测量 |
| Agent 初始化 | 短入口、开发指南和三个项目 Skills 已编写 | 新会话自动发现、行为收益已实测 |

2026-09-28 环境复核：Docker Desktop Linux 引擎已运行，分配约 22 CPU / 24 GiB 内存；
本机 C/D/E 盘分别约有 51/91/57 GiB 可用空间。CareerAct PostgreSQL 容器健康，端口为
`localhost:15432`。此前 GHCR 下载阻塞已解除，API、Browser、Worker 镜像均已生成。

## 下一项任务：接管授权与会话互斥边界

操作入口见[开发指南](DEVELOPMENT.md)。当前本机 `.env` 与 `apps/web/.env.local` 仅用于开发，
凭据未进入 Git；本机 `OPENAI_API_KEY` 与 `DASHSCOPE_API_KEY` 已确认非空但不记录值。LiteLLM
健康接口、模型列表、两个别名的真实请求和 BFF Agent SSE 均已通过；Temporal 已启动并通过
健康 Workflow。Steel 会话创建、虚构表单填写/点击/结果读取和释放已在宿主机及 Browser
容器内通过；Viewer 画面、鼠标和普通键盘输入已验证，完整接管体验仍有已知限制。

验收按层推进，不一次铺开全部业务：

1. 接管授权代理、写入互斥边界及 Viewer 已知限制的处理方案；Docling 基础解析已通过，
   扫描件 OCR、中文 PDF、复杂表格及生产模型资源预置留到材料纵切片验收。
2. 实现职业档案这一条最小领域纵切片，再扩展材料版本和岗位记录。
3. 记录峰值内存、磁盘增长和明确失败；再选择一条真实网申路径做业务闭环。

前一步失败时先定位边界，不靠更换整套架构、升级硬件或购买云资源掩盖问题。
模型调用可能计费；真实站点登录、提交与消息发送按具体授权执行，不拿真实申请当普通自动化测试。
本地验证无法证明云 IP 下的招聘站点风控与公网体验，后续仍需单独验证。

## 更新方式

完成一个阶段或改变下一步时，更新上面的事实和以下简短记录，不为每次工具调用写日志：

- 验证记录：日期、代码版本或未提交差异范围、命令/场景、实际结果。
- 未验证/阻塞：缺少的条件、mock 的边界及下一步，不把失败写成完成。
- 证据：链接可公开的测试或脱敏记录；原始账号数据和截图放被忽略的本地位置。

本次初始化提交已完成；本轮已启动 PostgreSQL、LiteLLM、API 和 Web，并完成两家模型供应商及
认证到 Agent SSE 的本地验证。Temporal Worker 已连接，SystemHealthWorkflow 真实执行返回
`ok`；本地 Temporal 存储改用被忽略的 `data/temporal`，解决命名卷写权限问题。
初次健康验证尚未覆盖恢复，后续隔离验收结果见下方。Browser Service `/health` 返回 `200` / `status=ok`，
但该接口仅证明进程存活。此前 Steel 下载取消的阻塞已解除，后续结果见下方。
本地 `.env` 和 Web `.env.local` 经 `git check-ignore` 确认为忽略文件，且未被 Git 跟踪。
提交前全套代码检查、本地与生产 Compose 静态校验通过；生产配置校验使用示例变量，未部署。
根目录与 Web Docker 构建上下文均排除真实环境文件。
凭据拦截已配置：本机启用 `.githooks/pre-commit`，Gitleaks 脱敏扫描暂存内容并阻止真实环境文件；
CI Secrets 工作流扫描完整历史。45 条已核对的上游历史误报/公开标识仅按精确指纹例外处理。
隔离临时仓库验证：干净示例可提交、强制暂存环境文件被拒、工作区改干净但暂存区含虚构凭据仍被拒。
远程 CI 尚未运行，远程分支保护尚未设置；本地 hook 并非不可绕过的安全边界。
凭据防护提交前：Ruff、mypy、17 个 pytest 通过；历史扫描在精确上游例外下通过，暂存区扫描通过。

本轮镜像与浏览器底座验收（基于 `c3406eb1b` 后的工作区改动）：

- API / Browser / Worker 镜像构建通过，Docker 报告大小分别约 560MB / 892MB / 2.72GB。
- 修复 Worker 默认安装 CUDA 依赖及 OpenCV 缺少 Linux 系统库；CPU Torch、OpenCV、Docling 导入通过。
- API 与 Browser 容器健康检查返回 200；独立测试队列中的 SystemHealthWorkflow 返回 `ok`。
- `scripts/smoke_steel.py` 宿主机和容器网络实测通过；未使用模型、真实账户或真实申请。
- Steel 增加真实健康检查和回环端口绑定；`docker compose up -d --wait steel` 通过。
- 冻结依赖同步、Ruff、mypy、17 个 pytest 通过。未修改 Web，本轮未重复前端检查。
- 尚未验收：Web 容器与完整生产 Compose、Docling 模型下载/解析、任务恢复、接管和租约隔离。

后续恢复与接管基础通道验收：

- `uv run --no-sync python -m scripts.smoke_temporal` 真实执行通过：等待状态重放、强杀 Worker、
  离线信号持久化、强杀并重启独立 Temporal 容器、同一个 Run 完成、取消及执行超时终态。
- 诊断任务只在独立测试队列注册，无业务外部写操作；不是生产任务状态机或副作用可靠性验收。
- 修正本地 Steel `DOMAIN`，避免 Viewer 生成不可用的 `0.0.0.0:3000` WebSocket 地址。
- `uv run --no-sync python scripts/smoke_steel.py --viewer-channel msedge` 通过：实际帧、鼠标、
  普通键盘输入和远端虚构表单结果一致，随后会话释放成功。
- 上游 Viewer 已知限制：1280×900 观察窗口可能裁切宽画布；`Ctrl+A` 未正确实现全选。
  本次通过范围为 1920×900 下的基础输入，不包含快捷键、中文输入法或完整人工接管体验。
- 仍需验证/实现：生产 Temporal PostgreSQL 拓扑、Activity 副作用处理、同源授权代理、
  会话写入互斥、完整 Web 容器链路及 Docling 模型资源。核心职业业务尚未编写。

完整容器拓扑本地验收（独立 `careeract-smoke` 项目）：

- Web standalone 镜像构建成功，固定 Node digest，真实凭据仅在运行时注入；构建不接受密钥参数。
- 首次迁移和再次启动迁移均成功；修复正式 Temporal 镜像缺少动态配置文件导致的重启失败。
- 添加 Web/API/LiteLLM/Steel 健康检查与启动依赖；避免 Web 可响应但 API 尚未就绪的竞态。
- `scripts/smoke_stack.py check --restart` 通过注册、Session、JWKS、BFF/JWT/API、
  Origin/匿名拒绝、退出登录，以及 Web/API 重启后的 Session 和公钥保持。
- 正式 Temporal Server + PostgreSQL + 容器 Worker 的 SystemHealthWorkflow 返回 `ok`；
  Browser、Steel、LiteLLM 内网健康检查通过。本轮没有传入真实模型 key，也没有执行模型调用。
- 独立 headless Edge 实际操作生产页面完成注册、进入工作台，无 pageerror。
- 期间一次 Temporal CLI 连接超时，随后 gRPC 健康检查和完整复测通过；未做长时间稳定性/压力测试。
- 当时 `npm audit --omit=dev` 为 0；全依赖审计的两项 high 开发依赖告警已在后续收尾修复（见下）。
- 此前“完整 Web 容器链路/正式 Temporal 拓扑未验收”的限制由本轮本地结果更新；
  公网 HTTPS、云环境、模型经部署拓扑的流式响应、业务任务恢复与浏览器安全隔离仍未验收。

依赖与启动稳定性收尾：

- 锁文件中 `@redocly/openapi-core` 1.34.19 → 1.34.20，移除其嵌套的 js-yaml 4.3.1，
  复用修复版本 4.3.2；`npm audit --audit-level=low` 为 0，Web lint/typecheck/build 通过。
- 隔离拓扑 `check --restart` 再次通过，未调用真实模型或读取供应商密钥。
- 复现了重建后的就绪空窗：gRPC 健康通过，但健康 Workflow 在 30s 后超时；
  History 未执行任务，同期 matching 日志出现 `Not enough hosts to serve the request`。
  后续队列出现 Worker poller，新的独立诊断任务成功。此证据不能证明此前 CLI 连接超时同根因。
- 冒烟脚本现先有界探测任务队列及 Workflow poller，再单次提交健康 Workflow；
  保留每次就绪失败的提示，不自动重发执行失败的任务。这不是生产就绪门禁或业务可靠性实现。
- 修正后完成三轮 Temporal/Worker 容器重建及三轮重启，六个健康 Workflow 全部成功；
  每次重启前两次探测均尚无 Workflow poller，随后通过。保留已有 PostgreSQL 卷，
  不是全新数据库冷启动，也不是长时间稳定性或负载测试；最终完整链路 `check` 再次通过。
- 本轮脚本 Ruff 格式/检查、mypy 通过；工作区差异及新增脚本的 Gitleaks 脱敏扫描无发现。
  隔离测试容器已停止清理，数据库卷保留，原 `careeract-dev` 环境不变。
- 网页交互验收采用可见 Computer Use 的协作约定已加入根 AGENTS；本次未进行网页操作。

Docling 基础解析验收（独立开发单元）：

- 新增 `scripts/smoke_docling.py`，在实际 Linux Worker 镜像内生成并解析虚构中文 DOCX
  和英文文本 PDF，核对成功状态及关键文本；没有使用私人材料或供应商 key。
- 首次 PDF 布局模型下载及解析约 75s；复用缓存、`--network none` 的新容器中两种格式
  均通过，PDF 约 9–10s。缓存约 164MiB，最终解析进程峰值 RSS 978.3MiB。
- 模型缓存保留在被忽略的 `data/docling-smoke/models`，临时容器清理；没有接入业务 API
  或 Temporal Activity，也没有给正式 Worker 增加缓存挂载。
- OCR 和表格识别在本次明确关闭，未证明扫描件、中文 PDF 或真实简历解析质量；
  正式部署需预置并固定已验证的模型资源，不能依赖运行时海外下载。
- 脚本按 Linux 容器执行，Ruff 格式/检查及 mypy 的 Linux 平台检查通过。

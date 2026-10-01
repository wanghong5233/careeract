# CareerAct 当前状态

更新：2026-09-30。项目进度与证据索引；具体任务在专题维护，操作参数与命令在开发手册维护。

## 阶段结论

已完成关键基建收尾和第一条职业业务功能：用户可在工作台维护、确认并保存职业档案，
刷新后恢复，跨用户读写隔离，过期版本不能覆盖新数据。Agent 已移到辅助面板。
这是一条可运行的本地业务路径，尚不是完整求职产品；全部基建、权限与公网部署未闭环。

产品围绕职业项目、档案、材料、岗位、申请、任务和结果组织。首要目标是自用、可复现、
可展示的工程代表作，再通过少量真实试用改善产品。采用渐进开发，不承诺短假期内公开
商业化；Star 与用户规模不是首次发布门槛。本地通过后再讨论短期云端验证，不预购季度
服务器，不默认购买或部署。模拟面试、收费、规模化推广、客户端扩展暂不展开。

## 与产品和架构的差距

| 能力 | 当前实现与证据 | 尚缺什么 |
| --- | --- | --- |
| Web 工作台 | 注册/登录、中文职业档案主区、概览、表单与可收起的 Agent 面板 | 岗位/申请/材料明确标记待开放；尚无申请闭环和结果报告 |
| 用户身份 | Better Auth → 同源 BFF → JWT/JWKS → API 真实链路，档案双用户隔离与退出后拒绝通过 | 材料/任务等后续对象所有权、生产认证配置；档案隔离不代表全产品授权 |
| 职业领域 | 职业档案领域对象/用例、PostgreSQL、0003 迁移、GET/PUT `/api/v1/profile`、版本条件保存 | 每用户一份当前已确认档案；未保存草稿仅在页面内，暂无历史版本浏览、材料导入和删除入口 |
| 职业 Agent | Agno、AG-UI、PostgreSQL、LiteLLM 接通，两家真实模型通过 | 仅有通用指令，未接档案、领域工具和业务动作；前端刷新生成新 threadId，未实现会话历史恢复 |
| 机会发现 | PRD 原有机会发现与托管需求保留；Agent 主动检索的范围和可行性仍在讨论 | 当前 Agent 未注册搜索/网页读取工具；尚无招聘检索、来源接入或持续巡检的真实验证 |
| 模型网关 | API 受限推理 Key、管理凭据分离、范围/预算/限流/停用验证通过 | 产品用户独立额度、BYOK 管理和加密存储；服务额度不等于用户权限 |
| 持久任务 | Dev Server 恢复/取消/超时通过；正式 Temporal + PostgreSQL + Worker 健康 Workflow 通过 | Worker 只有健康 Workflow，无解析/求职 Activity、业务任务状态回写和恢复 |
| 浏览器 | Steel/Playwright 虚构表单读写、持久租约、签名控制、停止/断连规则通过 | 产品授权记录、生产连接隔离、同源 Viewer、browser-use 业务执行及站点适配；控制入口默认关闭 |
| 材料 | Tiptap/React PDF 依赖已安装；Docling 虚构中文 DOCX、英文文本 PDF 和缓存离线解析通过 | 编辑器/PDF 导出页面、上传和对象存储实现、版本/审批、解析 Activity；中文 PDF/OCR/表格和正式模型资源预置待验收 |
| 部署运营 | 四应用镜像与生产 Compose 拓扑已在本地隔离验证；开发基础服务仅绑定回环 | 公网 HTTPS、域名/备案、云资源峰值、备份恢复、云 IP 风控与长期稳定性未完成 |

档案已形成基础业务链路；材料、浏览器和运营的剩余集成随相应功能完成。
PRD 的网申、招聘沟通与托管方向保留，不用无限补通用基建来推迟真实业务。

## 工作优先顺序

| 顺序 | 目标与状态 | 进入条件或限制 |
| --- | --- | --- |
| 当前 | [工作台形态研究与原型](../topics/workspace/README.md)：完整功能入口已复核；已核实 Manus 2.0 / Cue、OpenAI dots / Space；形态已确认采用“Agent 主创的共创职业工作室＋常驻职业伙伴”，职业路线作为项目视图 | 设计草稿冻结；不再维护独立原型细节，进入正式 `apps/web`。完整功能入口继续保留，未改 PRD |
| 接下来 | 一条真实材料 Agent 主创路径贯穿 Agent、领域数据和界面 | Agent 依据已确认背景生成 Diff，用户反馈/精确修正后保存版本；刷新恢复、跨用户隔离、旧提议不能覆盖新正文 |
| 暂缓 | 机会检索、真实浏览器投递及托管 | 检索供应商/质量/成本待实测；浏览器按[开放检查](DEVELOPMENT.md#浏览器开放前检查)接入 |
| 暂缓 | 公网部署、收费和规模化推广 | 本地真实路径通过后再验证云资源及运营条件，不预购服务器 |

当前表单只证明档案持久化与隔离，不是最终产品形态。后续对象仍须验证各自所有权；
框架管理权限不等于产品权限，具体边界及网关参数见[开发手册](DEVELOPMENT.md#身份与权限边界)。
本地选型研究位于 `docs/topics/architecture-selection/README.md`；第 12 节是机会检索候选依据，
不代表已完成集成。研究仍为私人资料，新克隆无需依赖它来运行现有代码。

## 已验证证据与复现入口

以下为截至 2026-09-29 的已有结果。基建收尾重新完成冻结依赖同步、Ruff、mypy、
默认 pytest（53 通过、6 跳过）、6 项 PostgreSQL/Steel/LiteLLM 真实集成以及 Web
lint/typecheck/build；本次未重复付费模型调用或完整部署重启检查。
档案专项通过真实 PostgreSQL 和本地完整 BFF 链路；可见页面已验收保存、刷新与冲突，
保存服务失败用浏览器内 503 替身验证。窄屏使用约 390px 同源 iframe 验证，不代表真机验收。
操作和验收命令统一维护在 [DEVELOPMENT](DEVELOPMENT.md)。

| 范围 | 证据入口 | 实际结果与边界 |
| --- | --- | --- |
| 职业档案 | [test_profiles.py](../../tests/api/test_profiles.py)、[smoke_profile.py](../../scripts/smoke_profile.py) | 实际迁移升级/回退后保留认证数据、真实 PostgreSQL 持久化、并发创建/更新、跨用户读写拒绝；真实注册/Session/BFF/JWT/API/数据库、Origin 检查、过期版本和退出后拒绝通过，无模型调用 |
| 最新代码检查 | [tests](../../tests)、[CI](../../.github/workflows/ci.yml) | 冻结依赖同步、Ruff、mypy、Web lint/typecheck/build 通过；开启档案 PostgreSQL 的全套测试 56 通过/6 跳过；全部集成开启时 61 通过/1 Steel 凭证校验失败，该项单独重跑通过，不能记作整轮 62 项全绿 |
| 部署认证 | [smoke_stack.py](../../scripts/smoke_stack.py) | 隔离 check --restart 通过注册、Session、JWKS、BFF/JWT/API、匿名/Origin 拒绝、退出与重启；API 无管理/供应商 Key、迁移无模型 Key，重复初始化成功 |
| 模型权限 | [test_model_gateway.py](../../tests/api/test_model_gateway.py) | 固定 OSS 网关与真实临时 PostgreSQL 验证范围、SSE、管理拒绝、预算/RPM/TPM、轮换/停用；模型输出用替身，无供应商费用 |
| 真实模型 | [agent_runtime.py](../../services/api/infrastructure/agent_runtime.py) | 两别名以受限 Key 请求通过；宿主机 Web 注册 → BFF → API → 真实模型 SSE → 退出通过，仅虚构内容，产生少量模型调用；未覆盖经 Caddy 的真实模型 SSE |
| 任务恢复 | [smoke_temporal.py](../../scripts/smoke_temporal.py)、smoke_stack | Dev Server 等待重放、强杀 Worker/Server、取消/超时通过；正式 PostgreSQL 拓扑健康 Workflow 和六轮重建/重启探测通过；不代表业务副作用恢复 |
| 浏览器控制 | [test_postgres_leases.py](../../tests/browser/test_postgres_leases.py)、[test_steel_executor.py](../../tests/browser/test_steel_executor.py) | 迁移/回退、跨进程竞争、真实 HTTP 签名/撤销和 Steel 旧连接断开通过；已知 raw CDP URL 仍可重连，不证明完整隔离 |
| Viewer 输入 | [smoke_steel.py](../../scripts/smoke_steel.py) | 1920×900 帧/鼠标/普通键盘通过；窄窗口裁切、Ctrl+A、中文输入及完整授权交接未解决/未验收；一次可见执行器验收因工具无法识别 URL 未执行 |
| 材料解析 | [smoke_docling.py](../../scripts/smoke_docling.py) | Linux CPU Worker 虚构 DOCX/文本 PDF、断网缓存解析通过；缓存约 164 MiB，单解析进程峰值约 978 MiB；不代表整机峰值或真实简历质量 |
| 凭据防护 | [.githooks/pre-commit](../../.githooks/pre-commit)、[check_secrets.py](../../scripts/check_secrets.py) | 本机 hook 启用；隔离暂存秘密/环境文件拒绝测试通过，最新差异/新源码扫描无发现；远程 CI/分支保护未验收 |

Steel 全量回归中的短时凭证失败尚未定位根因；没有放宽时效校验或修改浏览器代码来绕过。
该能力仍默认关闭，不阻塞手动档案使用；开放浏览器前须复核时钟与凭证时效的稳定性。

## 环境与协作状态

- 开发地址 `http://localhost:3100`，API 为 8000；3000 曾被系统进程占用，因此用进程
  环境同步覆盖认证 URL、issuer/audience 和 JWKS，未改真实环境文件。新增迁移已应用本地库，
  API 已重启加载档案接口；AgentOS 同步数据库连接设置 5 秒连接超时，避免连接无限等待。
  可见浏览器仅使用新建虚构账号，未改用户真实档案；本地验收账号保留在开发库。
- 本机 32 GB 内存、Ultra 7 155H，具备开发起步条件；2026-09-28 Docker 预算约 24 GiB。
  整套服务峰值及云端 4 核 16 GB 承载程度仍需测量，不能凭规格保证上线。
- 工程管理整理已落地：长期方向保留 PRD/ARCHITECTURE，手册归 handbook，专题归 topics；
  SOP 与文档职责见[开发手册](DEVELOPMENT.md#单人开发流程)。文档整理与设计原型未修改业务代码。
  工程协作 Skill 与调研在 `.agents/skills/careeract-engineering/`；实际提效仍待后续交付验证。
  文档验收通过：18 份 Markdown 的 81 处本地链接、4 个 Skill、公开/私人路径忽略边界与
  两份迁移研究的内容完整性均已核对；无旧路径引用。这是原型制作前的文档整理验收。
- 2026-09-30 设计基线提交检查：冻结依赖同步、Ruff、mypy、pytest（55 通过、7 跳过）、
  Web lint/typecheck/build、原型 JS 语法、90 处本地文档链接及私人资料忽略边界通过。
  Web 初次类型检查遇到旧路由生成缓存，清理对应缓存并重新 typegen 后通过；未修改业务源码。
  未开启真实外部集成；工作台形态已完成用户确认，正式业务界面尚未实现材料协作闭环。
- 原型覆盖复核：全部 PRD 核心能力组已有入口与代表 UI，具体“交互样例 / 界面预留”见
  [需求覆盖表](../topics/workspace/DESIGN.md#需求覆盖复核)。本机 `career/` 作为真实需求与
  后续 Dogfood 来源的读取规则已进入 AGENTS；未导入私人正文，未修改正式业务源码或 PRD。

新增事实时直接更新对应结论和证据，移除被替代的“尚未/下一步”表述。
仅保留仍影响决策的失败和限制，不把历史临时故障永久写成架构阻塞。

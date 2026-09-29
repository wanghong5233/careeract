# CareerAct 当前状态

更新：2026-09-29。只维护当前结论、下一步和可复查证据，不逐轮追加开发日志。

## 阶段结论

当前是已通过本地关键集成的工程骨架，可以开始第一条职业业务功能。
尚不是可用的求职产品，也不能称为全部基建、全部权限或公网部署已经闭环。
当前页面用于验证注册登录和 Agent 流式交互，不能作为 PRD 工作台的验收结果。

产品围绕职业项目、档案、材料、岗位、申请、任务和结果组织。首要目标是自用、可复现、
可展示的工程代表作，再通过少量真实试用改善产品。采用渐进开发，不承诺短假期内公开
商业化；Star 与用户规模不是首次发布门槛。本地通过后再讨论短期云端验证，不预购季度
服务器，不默认购买或部署。模拟面试、收费、规模化推广、客户端扩展暂不展开。

## 与产品和架构的差距

| 能力 | 当前实现与证据 | 尚缺什么 |
| --- | --- | --- |
| Web 工作台 | 注册/登录、侧栏外壳、assistant-ui 对话与 SSE | 档案/岗位/申请/材料均是占位；没有真实业务页面、工作台概览和结果报告 |
| 用户身份 | Better Auth → 同源 BFF → JWT/JWKS → API 真实链路通过 | 业务对象所有权验收、生产认证配置；登录成功不代表完整授权 |
| 职业领域 | 目录职责、ActorContext、事务/对象存储端口已有定义 | domain 尚无职业实体，API 尚无职业档案等产品 CRUD 和领域迁移 |
| 职业 Agent | Agno、AG-UI、PostgreSQL、LiteLLM 接通，两家真实模型通过 | 仅有通用指令，未接档案、领域工具和业务动作；前端刷新生成新 threadId，未实现会话历史恢复 |
| 模型网关 | API 受限推理 Key、管理凭据分离、范围/预算/限流/停用验证通过 | 产品用户独立额度、BYOK 管理和加密存储；服务额度不等于用户权限 |
| 持久任务 | Dev Server 恢复/取消/超时通过；正式 Temporal + PostgreSQL + Worker 健康 Workflow 通过 | Worker 只有健康 Workflow，无解析/求职 Activity、业务任务状态回写和恢复 |
| 浏览器 | Steel/Playwright 虚构表单读写、持久租约、签名控制、停止/断连规则通过 | 产品授权记录、生产连接隔离、同源 Viewer、browser-use 业务执行及站点适配；控制入口默认关闭 |
| 材料 | Tiptap/React PDF 依赖已安装；Docling 虚构中文 DOCX、英文文本 PDF 和缓存离线解析通过 | 编辑器/PDF 导出页面、上传和对象存储实现、版本/审批、解析 Activity；中文 PDF/OCR/表格和正式模型资源预置待验收 |
| 部署运营 | 四应用镜像与生产 Compose 拓扑已在本地隔离验证；开发基础服务仅绑定回环 | 公网 HTTPS、域名/备案、云资源峰值、备份恢复、云 IP 风控与长期稳定性未完成 |

支持档案开发的基础链路已经具备；材料、浏览器和运营的剩余集成随相应功能完成。
PRD 的网申、招聘沟通与托管方向保留，不用无限补通用基建来推迟真实业务。

## 权限专项的完成边界

- 已完成模型网关最小权限：API 必填 `LITELLM_API_KEY`，无 master 回退；迁移只需数据库
  配置。部署仅给 LiteLLM 与一次性初始化进程管理 Key，供应商 Key 只给 LiteLLM。
- 运维脚本支持准备、注册、检查、轮换和停用；重复初始化不改已有策略，blocked 记录不
  自动启用。本机 `.env.litellm` 已忽略，原供应商 Key 未修改，真实值不输出。
- 原型服务总策略为两模型别名、Chat Completions/模型列表路由、5 美元预算、`30d` 周期、
  30 RPM、60,000 TPM、单在途请求。超限拒绝，无产品排队；异步释放并发计数可能短暂
  返回 429。网关估算不等于供应商账单或绝对费用上限，试用前仍需复核。
- 全产品权限尚未完成：职业数据、材料下载、Agent 会话历史、业务任务、浏览器接管均须
  随功能接入验证归属和撤销。浏览器服务签名证明调用来源，不代替真实用户授权。
- 产品管理员后台暂不实现；云厂商控制台管理云资源，不能代替业务权限。当前账号按普通
  产品用户使用。具体边界和操作见[开发指南](DEVELOPMENT.md#身份与权限边界)。

## 下一项：可用工作台与职业档案

交付一条从页面到数据库的完整业务路径，不以接口存在或静态页面漂亮作为完成。

1. 工作台以职业内容为主区：真实档案入口、当前档案概览和下一步提示，Agent 作为辅助
   交互区。未实现的岗位/材料/申请入口明确标注，不能伪装为可操作功能。
2. 手动维护教育、经历、项目/成果、技能，以及求职目标和约束；用户填写和确认的信息
   才作为职业事实。首轮不依赖文件导入、浏览器或自动生成简历。
3. 实现领域对象、用例、PostgreSQL 存储、新 Alembic migration、`/api/v1` REST 和
   同源 BFF；遵循[接口约定](../../services/api/routes/README.md)，含输入校验和过期版本写入拒绝。
4. 验收空态、编辑、保存、错误反馈、重新登录/刷新后保留，以及两个用户不能互相读写。
   身份来自已验证的 Session/JWT，不能信任客户端提供的 user_id。
5. 持久化通过后，让 Agent 读取当前用户已确认的档案回答问题；验证更新后读取新版本、
   另一用户的上下文不混入。Agent 改档案与外部动作留给具有明确授权的后续用例。

页面验收优先可见浏览器，区分实际操作与后台 HTTP/自动化检查。保持简洁的中文工作台，
不继续扩展模板自带的推理 Trace、附件或语音展示来冒充 PRD 能力。
随后做材料版本与岗位记录，再按[浏览器专项计划](plans/BROWSER_SAFETY_PLAN.md)完成隔离和接管，
选择一条用户在场的真实网申路径，形成申请记录、结果证据与报告。

## 已验证证据与复现入口

以下为截至 2026-09-29 的已有结果。基建收尾重新完成冻结依赖同步、Ruff、mypy、
默认 pytest（53 通过、6 跳过）、6 项 PostgreSQL/Steel/LiteLLM 真实集成以及 Web
lint/typecheck/build；本次未重复付费模型调用或完整部署重启检查。
操作和验收命令统一维护在 [DEVELOPMENT](DEVELOPMENT.md)。

| 范围 | 证据入口 | 实际结果与边界 |
| --- | --- | --- |
| 最新代码检查 | [tests](../../tests)、[CI](../../.github/workflows/ci.yml) | Ruff 格式/检查、mypy、开启 PostgreSQL/Steel/LiteLLM 集成的 59 项 pytest 通过；此前 Web lint/typecheck/build 通过 |
| 部署认证 | [smoke_stack.py](../../scripts/smoke_stack.py) | 隔离 check --restart 通过注册、Session、JWKS、BFF/JWT/API、匿名/Origin 拒绝、退出与重启；API 无管理/供应商 Key、迁移无模型 Key，重复初始化成功 |
| 模型权限 | [test_model_gateway.py](../../tests/api/test_model_gateway.py) | 固定 OSS 网关与真实临时 PostgreSQL 验证范围、SSE、管理拒绝、预算/RPM/TPM、轮换/停用；模型输出用替身，无供应商费用 |
| 真实模型 | [agent_runtime.py](../../services/api/infrastructure/agent_runtime.py) | 两别名以受限 Key 请求通过；宿主机 Web 注册 → BFF → API → 真实模型 SSE → 退出通过，仅虚构内容，产生少量模型调用；未覆盖经 Caddy 的真实模型 SSE |
| 任务恢复 | [smoke_temporal.py](../../scripts/smoke_temporal.py)、smoke_stack | Dev Server 等待重放、强杀 Worker/Server、取消/超时通过；正式 PostgreSQL 拓扑健康 Workflow 和六轮重建/重启探测通过；不代表业务副作用恢复 |
| 浏览器控制 | [test_postgres_leases.py](../../tests/browser/test_postgres_leases.py)、[test_steel_executor.py](../../tests/browser/test_steel_executor.py) | 迁移/回退、跨进程竞争、真实 HTTP 签名/撤销和 Steel 旧连接断开通过；已知 raw CDP URL 仍可重连，不证明完整隔离 |
| Viewer 输入 | [smoke_steel.py](../../scripts/smoke_steel.py) | 1920×900 帧/鼠标/普通键盘通过；窄窗口裁切、Ctrl+A、中文输入及完整授权交接未解决/未验收；一次可见执行器验收因工具无法识别 URL 未执行 |
| 材料解析 | [smoke_docling.py](../../scripts/smoke_docling.py) | Linux CPU Worker 虚构 DOCX/文本 PDF、断网缓存解析通过；缓存约 164 MiB，单解析进程峰值约 978 MiB；不代表整机峰值或真实简历质量 |
| 凭据防护 | [.githooks/pre-commit](../../.githooks/pre-commit)、[check_secrets.py](../../scripts/check_secrets.py) | 本机 hook 启用；隔离暂存秘密/环境文件拒绝测试通过，最新差异/新源码扫描无发现；远程 CI/分支保护未验收 |

## 当前环境与未提交工作

- 开发地址 `http://localhost:3100`，API 为 8000；3000 曾被系统进程占用，因此用进程
  环境同步覆盖认证 URL、issuer/audience 和 JWKS，未改真实环境文件。本轮只读复核登录页、
  API health、LiteLLM readiness 均为 200，四个开发容器运行中。本轮未读取用户浏览器
  登录态或截图，不把 URL 提示当成实际页面检查。
- 本机 32 GB 内存、Ultra 7 155H，具备开发起步条件；2026-09-28 Docker 预算约 24 GiB。
  整套服务峰值及云端 4 核 16 GB 承载程度仍需测量，不能凭规格保证上线。
- 基建收尾按文档流程、模型权限、浏览器控制分别提交；文档流程为 `08c06f0dc`，
  模型凭据分离为 `35b7907a1`，浏览器持久租约/签名控制/执行器生命周期随本状态更新提交。
  用户授权本地提交，未 push；业务开发从此基线继续，避免再积压不同目的的改动。
- 文档职责：本目录集中维护工程协作资料；本文件看现状，DEVELOPMENT 看操作，SKILLS 看三个
  项目技能，plans/BROWSER_SAFETY_PLAN 看浏览器开放门槛。docs 顶层保留私有 PRD/ARCHITECTURE，
  docs/archive 保留历史选型/硬件依据。目录与新增文件规则见 [AGENTS](../../AGENTS.md#documentation)。
- 独立终端监控方案已放弃，个人 Skill 已删除，仓库内无引用；正常终端执行与简短进度
  说明继续使用，不再为此增加项目基建。

新增事实时直接更新对应结论和证据，移除被替代的“尚未/下一步”表述。
仅保留仍影响决策的失败和限制，不把历史临时故障永久写成架构阻塞。

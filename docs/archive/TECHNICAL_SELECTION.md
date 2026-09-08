# CareerAct 技术选型调研与依据

> 文档类型：架构调研与决策证据  
> 最终架构：[ARCHITECTURE.md](../ARCHITECTURE.md)  
> 对应需求：[PRD.md](../PRD.md)  
> 核验日期：2026-09-07

## 1. 文档边界

本文保存组件候选、社区规模、许可证、价格、取舍依据和验证项，避免把调研过程堆入主架构文档。

最终采用什么、各层如何连接，以 `ARCHITECTURE.md` 为准。Star 只用于排除缺少社区检验的项目，不能替代对许可证、架构适配、维护活跃度和真实运行结果的判断。

## 2. 已确定的技术基线

- 产品前端：自有 CareerAct Agent Workspace；
- Web 框架：Next.js；
- 基础 UI：shadcn/ui；
- Agent 交互区域：assistant-ui；
- 材料编辑：Tiptap；
- 材料解析：Docling；
- PDF 生成：`diegomura/react-pdf` 的 `@react-pdf/renderer`；
- 身份认证：Better Auth；
- 领域后端：FastAPI；
- Agent Runtime：Agno AgentOS；
- 前后端 Agent 协议：AG-UI；
- 模型网关：LiteLLM OSS；
- 长期业务数据：PostgreSQL；
- 持久任务：Temporal；
- HTTPS 与同源反向代理：Caddy；
- 浏览器基础设施：国内自托管 Steel Browser OSS；
- 确定性网页执行：Playwright；
- 智能网页执行：browser-use OSS；
- 原始材料和结果证据：国内 OSS / COS / TOS。

## 3. 社区规模与成熟度快照

以下为 2026-09-07 GitHub 快照，均核验了许可证和最近提交。

### 3.1 最终采用

- Next.js：约 142k Star，MIT，当日活跃；
- shadcn/ui：约 123k Star，MIT，前一日活跃；
- assistant-ui：约 12k Star，MIT，当日活跃；
- Tiptap：约 38k Star，MIT，持续维护；
- Better Auth：约 30k Star，MIT，持续维护；
- FastAPI：约 102k Star，MIT，持续维护；
- Agno：约 42k Star，Apache-2.0，当日活跃；
- AG-UI：约 15.8k Star，MIT，持续维护；
- LiteLLM：约 58k Star，MIT Core + 商业 Enterprise 分区许可，当日活跃；
- Temporal：约 23k Star，MIT，当日活跃；
- Caddy：约 75k Star，Apache-2.0，持续维护；
- Playwright：约 96k Star，Apache-2.0，持续维护；
- browser-use：约 113k Star，MIT，持续维护；
- Steel：约 7.6k Star，Apache-2.0，持续维护；
- Docling：约 66k Star，MIT，持续维护；
- `diegomura/react-pdf`：约 17k Star，MIT，npm 包为 `@react-pdf/renderer`，用于 PDF 生成；

Steel 的社区规模明显小于 Playwright 和 browser-use，并且仍处在快速发展阶段。选择它是因为其 OSS 版本可在国内 Docker 自托管，许可证宽松，并支持远程 CDP、持久 Profile、实时画面和人工接管；真实招聘网站兼容性仍需通过日常开发和 Dogfood 持续验证。

### 3.2 重点比较但未采用

- LobeHub：约 82k Star，产品完成度高，但 Community License 对衍生产品和商业开发存在额外授权边界；
- OpenHands：约 86k Star，Agent Workspace 形态成熟，但围绕代码、Git、终端、Sandbox 和 OpenHands Agent Server 构建；
- CopilotKit：约 37k Star，MIT，Agent 与应用状态协作能力强，但 Agno 集成和部分持久线程能力不如当前方案边界清晰；
- Mastra：TypeScript Agent / Workflow 框架，核心采用 Apache-2.0；当前 Python 领域后端已选择 Agno，不并行维护第二套 Runtime；
- LangGraph / PydanticAI：Agent SDK 能力成熟，但需要额外补齐 Host、前端协议和运行管理，不替代当前 Agno AgentOS；
- LibreChat / AnythingLLM / Open WebUI / Dify：完整度较高，但以通用聊天或 RAG 为中心，部分项目还有品牌、多租户或商业许可边界，不适合作为职业 Agent Workspace 底座；
- Refine：约 36k Star，MIT，适合 CRUD 和内部管理系统，不适合作为个人 Agent Workspace 的产品骨架；
- React Admin：约 27k Star，MIT，同样偏后台管理系统；
- Stagehand：约 24k Star，MIT，语义浏览器原语成熟，但需要本项目承担更多 Agent 控制流；
- Skyvern：约 23k Star，AGPL-3.0，工作流完整，但闭源商业服务需要额外合规或商业许可；
- Hatchet：约 7.9k Star，MIT，自托管轻量，但生产历史和生态规模不如 Temporal；
- tool-ui：约 774 Star，MIT，只提供可复制的工具卡示例；社区检验不足以作为关键依赖，因此不进入主选型；
- Prefect：约 24k Star，Apache-2.0，更偏数据与任务编排；
- Celery：约 29k Star，成熟任务队列，但长等待、HITL 和业务恢复需要自建状态机。

## 4. 前端选择

### 4.1 产品形态

CareerAct 不是聊天产品。主体是围绕职业目标持续工作的 Agent Workspace：

- 左侧组织职业项目、任务、材料、岗位和申请；
- 中间呈现当前材料、岗位、计划、流程或报告；
- Agent 交互区域负责指令、解释、执行进度、工具结果和审批；
- 远程浏览器和材料 Diff 在任务需要时进入主要工作区；
- Agent 修改的是后端职业对象，不把聊天线程当作业务真相。

Cursor、Codex 和 OpenHands Agent Canvas 是交互参考，不是代码底座。

### 4.2 为什么选择 Next.js + shadcn/ui

- 社区规模大、维护持续、商业使用边界清晰；
- 适合 Web 零安装分发、路由、认证和 BFF；
- shadcn/ui 以源码复制方式使用，不形成难以修改的 UI 黑盒；
- 与 assistant-ui、Tiptap 和 Better Auth 的 React 生态一致。

### 4.3 为什么不 Fork LobeHub

LobeHub 完整的是通用聊天与 Agent 产品。CareerAct 仍需重建职业档案、项目、材料、岗位、申请、沟通、托管服务和 Browser Service。深改后的复用收益下降，同时触发 Community License 的商业衍生边界。

如果未来获得明确商业授权，可以重新评估，但不作为当前开源底座。

### 4.4 为什么不 Fork OpenHands Agent Canvas

OpenHands 的工作台形态与 CareerAct 很接近，适合参考侧栏、任务、文件、自动化和多面板布局。但其前端直接适配 OpenHands Agent Server、Automation Server、终端、Git 和 Sandbox。改接 Agno 并替换为职业领域对象，需要重写主要 API 与状态模型。

OpenHands 还处于拆分 Agent Canvas、Agent Server 和 Automation 仓库的迁移期，因此只参考产品结构，不直接 Fork。

### 4.5 为什么选择 assistant-ui

assistant-ui 只承担 Agent 交互区域：

- 流式消息；
- Thread、Message、Composer；
- 工具调用和结果；
- 取消、重试和交互状态；
- AG-UI Runtime Adapter；
- RealtimeVoiceAdapter：实时双向语音、打断、转写和会话状态。

它不接管职业领域状态，符合“产品后端拥有业务真相”的原则。官方 `with-ag-ui` Starter 用于快速验证和提取交互模块，不把示例应用直接当作 CareerAct 完整前端。assistant-ui 的 AG-UI Interrupt 与线程列表仍包含实验性 API，因此正式审批、待处理事项和会话持久化由 CareerAct 后端管理。

模拟面试不需要新增语音框架。文字交互继续使用 AG-UI；实时语音由 assistant-ui 的 RealtimeVoiceAdapter 接入，LiteLLM OSS Proxy 已提供 Realtime WebSocket 和面向浏览器的 WebRTC 接口。领域后端负责组装实际投递材料、JD、公司和面经上下文，并保存转写与训练结果。实时语音模型产生的 Token 或音频用量仍属于模型供应商费用。

CopilotKit 更擅长 Agent 直接读取和修改前端状态，但 CareerAct 的正式动作应通过领域后端执行。若实际开发证明 assistant-ui 无法稳定映射 Agno 的 AG-UI/HITL，再替换交互层，不并行维护两套实现。

### 4.6 材料处理

- Tiptap：结构化材料编辑和交互式修改；
- Docling：PDF、DOCX 等原始材料解析与结构化提取；
- `@react-pdf/renderer`：首版 PDF 简历与报告生成；
- 对象存储：保存原始文件、锁定版本和结果证据；
- CareerAct 领域后端：管理事实来源、版本、Diff、审批和回滚。

编辑器或解析器不能替代材料版本和事实边界。

## 5. 后端与 Agent Runtime

### 5.1 FastAPI

CareerAct 的主要智能执行、文档处理和 Computer Use 均在 Python 生态。FastAPI 作为领域 API 和 Agno 宿主，可以减少跨语言服务胶水。

Next.js 仍负责 Web 页面、认证入口和必要 BFF；这不是重复建设两个后端，而是产品 Web 层与 Python 领域/Agent 层分工。

### 5.2 Agno AgentOS

选择依据：

- Apache-2.0；
- Python 与 FastAPI 原生；
- Agent、Team、Workflow、Run、Session、HITL 和 Trace；
- AgentOS v3 原生 AG-UI；
- 固定版本并将源码放入项目 `vendor/`，可以直接本地调试；只有确需补丁时才修改上游源码；
- 不强制使用 Agno Control Plane。

Agno v3 已提供持久后台 Job 和 HITL，但不拥有职业领域数据。Temporal 仍用于跨 Agent、浏览器、通知渠道和长时间用户等待的统一业务编排，使持久执行不绑定单一 Agent Runtime。

### 5.3 上下文组装

长期职业上下文不依赖聊天历史拼接，也不在首版引入独立向量数据库：

- 按用户、项目、岗位、材料版本和对象关系结构化查询；
- 英文长文本使用 PostgreSQL Full Text Search，中文材料使用规范化子串检索与 `pg_trgm` 相似度检索；
- 锁定实际投递版本，后续修改不能覆盖历史上下文；
- 只装配当前用户有权访问的数据；
- 每条正式事实保留来源引用；
- 按任务设置上下文长度预算。

只有评测证明结构化查询和全文检索不足时，再评估 pgvector。

### 5.4 LiteLLM

LiteLLM OSS Core / Proxy 作为模型网关，负责统一 API、BYOK、多供应商路由、虚拟 Key、预算和用量，并通过 Realtime WebSocket / WebRTC 路由受支持的实时语音模型。只使用 MIT 范围，不启用 `enterprise/` 目录中需要商业许可证的能力。

## 6. 持久任务选择

PRD 将“已发起任务后台续跑”和“长期无人值守托管”明确区分，因此需要独立于 Agent Run 的持久执行层。

### 6.1 选择 Temporal

Temporal 负责：

- 用户关闭网页后的任务续跑；
- 进程或 Worker 重启后的恢复；
- 定时巡检；
- 长时间等待用户事件；
- Activity 超时、重试和取消；
- 外部写操作的执行账本、结果不确定处理和人工对账；
- 托管服务的暂停与撤销。

选择 Temporal 而不是 Hatchet，主要因为无人值守和不可逆外部动作是产品核心，可靠性优先于少量部署便利。Temporal 的生产历史、社区规模和持久执行语义更成熟。

### 6.2 与 Agno 的边界

- Temporal Workflow：业务阶段、等待、重试、调度和恢复；
- Temporal Activity：调用 Agno Run、Browser Service、数据库或通知渠道；
- Agno：单个智能步骤中的推理和工具选择；
- PostgreSQL：最终业务状态；
- Temporal Event History：执行恢复依据。

Agent Run 成功不等于申请成功；必须由 Activity 读取外部结果并回写领域状态。Temporal Activity 可能重复执行，而招聘网站不接受客户端幂等键，因此结果不确定的提交或发送动作禁止自动重试。

### 6.3 部署取舍

- 本地开发：Temporal CLI Dev Server，可通过 `--db-filename` 保存调试数据；
- 国内最小运营：官方 `temporalio/server` 镜像 + PostgreSQL，不使用 `start-dev`；
- 生产托管可选 Temporal Cloud；
- 业务、Agent、LiteLLM 与 Temporal 可以共用一个 PostgreSQL 实例，但使用独立数据库或 Schema。

单机部署没有高可用，但服务器重启后可以依靠 PostgreSQL 恢复 Workflow。固定 Temporal 版本、每日备份并在升级时执行官方 Schema Migration，即可满足 OPC 初期运营。

## 7. Browser Service / Computer Use

### 7.1 最终组合

- Steel：浏览器会话、Profile、远程 CDP、实时画面和人工接管；
- Playwright：稳定页面的确定性操作、文件上传、等待和读回；
- browser-use：未知页面、结构变化和语义/视觉操作；
- CareerAct 站点适配器：BOSS、猎聘和企业官网业务流程；
- Temporal：调度浏览器任务、处理等待、超时、重试和取消。

没有单一组件同时提供以上所有能力。组合不是重复造轮子，而是按职责使用各自成熟部分。

### 7.2 为什么 Playwright 是默认执行路径

PRD 要求日期、下拉、级联、附件、暂存、预览和保存后核验。对已知页面，确定性代码比完全自主 Agent 更可靠、更便宜，也更容易回归。

### 7.3 为什么需要 browser-use

企业官网和招聘平台页面结构不统一，固定选择器会失效。browser-use 负责页面探索和语义操作，但其 `done` 结果不能直接作为业务成功，仍需确定性读取或站点适配器验收。

### 7.4 为什么选择自托管 Steel Browser OSS

Steel 补齐 browser-use OSS 不提供的多用户浏览器基础设施：

- 隔离会话和 Profile；
- 持久登录态；
- 远程 CDP；
- 实时查看与人工接管；
- 浏览器生命周期；
- Cloud 下的代理、文件和验证码能力。

本地开发和国内最小运营均使用 Steel Browser OSS。`.cache` 与 Profile 目录挂载持久卷，Steel API 和 CDP 只在 Docker 内网开放。最小实例同时运行一个浏览器会话，其他任务排队；需要更多并发时增加 Steel 实例或浏览器节点。

Steel OSS 不提供 Cloud 的 Files、Credentials、托管代理和 CAPTCHA API，但这些差异不阻塞 CareerAct：

- 附件由 CareerAct 从国内对象存储下载后交给 Playwright 上传；
- 用户在隔离浏览器中直接登录，Profile 持久保存登录态；
- 验证码交给用户处理，不接入自动绕过服务；
- 国内招聘网站默认使用国内云服务器出口，不依赖海外代理。

Steel 原始 `debugUrl` 持有者可以直接查看和操作会话，因此不能下发给浏览器。CareerAct 通过同源服务端代理、一次性短期授权、撤销和访问审计提供人工接管。

### 7.5 未采用方案

- Stagehand：适合确定性代码与语义动作混合，但首版需要自行承担更多 Agent 控制循环；
- Skyvern：更接近完整 RPA 平台，但 AGPL-3.0 与交互接管成熟度不符合当前商业边界；
- Steel Cloud、Browser Use Cloud：仅作为后续扩容或故障备选，不是国内首版运行依赖；
- Browserbase：成熟托管浏览器，但属于商业服务，不是可修改的开源基础设施。

## 8. 身份、数据与外部渠道

### 8.1 Better Auth

Better Auth 负责 Web Session、账户认证和 JWT/JWKS。浏览器只访问同源 Next.js BFF；BFF 验证 Session，通过 JWT Plugin 获取短期 Token 并转发给 FastAPI / AG-UI。FastAPI 与 AgentOS 按固定 issuer、audience、过期时间和 JWKS 验证 Token，以 `sub` 作为统一用户 ID。写请求执行 Origin / CSRF 检查，FastAPI 不向浏览器开放宽泛 CORS。

选择依据是 MIT、约 30k Star、Next.js 原生、代码内配置和不按 MAU 收取 OSS 许可费。

### 8.2 敏感数据

- BYOK 使用信封加密，主密钥放在部署环境的 Secret Manager，不与数据库密文同库存放；
- 招聘平台优先由用户在隔离浏览器直接登录，不采集明文密码；
- 对象存储默认私有，通过短期签名 URL 访问；
- Steel Profile、任务、材料和 Trace 均绑定用户；
- Steel 原始 `debugUrl` 不返回浏览器，接管通过同源服务端代理和一次性短期授权完成；
- 支持撤销托管、删除 Profile、密钥、材料和账户数据。

### 8.3 外部渠道

招聘邮件、通知和搜索没有一个需要提前绑定的通用框架：

- Gmail 使用 Gmail API；
- Outlook 使用 Microsoft Graph；
- 其他邮箱使用授权 IMAP 或转发；
- 公司调研优先复用 Browser Service 和模型搜索工具；
- 所有渠道通过 CareerAct Adapter 接入领域后端。

具体供应商在对应功能里程碑确定，不影响核心架构。

### 8.4 执行安全与补偿

- Temporal 按用户、平台和动作类型执行动态限流；
- 平台风控或账号异常触发站点级写操作熔断；
- CareerAct 通过执行账本对账业务状态和 Temporal 状态；
- 外部成功但内部未确认时标记 `uncertain`，禁止自动重试；
- 回写失败、Worker 崩溃和渠道超时通过补偿任务或人工对账处理。

## 9. 许可证边界

- MIT：Next.js、shadcn/ui、assistant-ui、AG-UI、Tiptap OSS、Better Auth、FastAPI、Temporal、browser-use、Docling、`diegomura/react-pdf`；
- Apache-2.0：Agno、Caddy、Playwright、Steel；
- PostgreSQL License：PostgreSQL 与 `pg_trgm`；
- 对象存储：许可证取决于最终采用的 S3 兼容实现或云服务；
- LiteLLM：`enterprise/` 以外为 MIT，Enterprise 目录使用商业许可证；
- LobeHub：Community License，不按无附加条件 Apache-2.0 处理；
- Skyvern：AGPL-3.0。

MIT / Apache-2.0 范围允许修改、私有部署和商业运营，但必须保留适用的 LICENSE、NOTICE 和版权声明。Fork 不会把上游版权转为本项目所有。

## 10. 成本记录

以下价格截至 2026-09-07，仅用于预算；采购前重新核验。

### 10.1 国内最小运营固定成本

- 一台 4 核 16GB、至少 80GB SSD 的国内 Linux 云服务器承载全部 Docker 服务；
- 阿里云 2026 年公开活动参考价为 149 元/月或 1599 元/年，上海在可选地域内；这是活动价，账号资格、库存和成交价以下单页为准；
- `.com` 域名注册约 85 元/年、续费约 95 元/年；
- 国内标准对象存储约 0.12 元/GB/月，早期材料规模通常低于 5 元/月；
- 中国大陆服务器使用域名对外服务前需要完成 ICP 备案，备案本身不收费。

自托管 Next.js、shadcn/ui、assistant-ui、Tiptap OSS、Better Auth、FastAPI、Agno AgentOS、Temporal、Caddy、LiteLLM OSS、PostgreSQL、Playwright、browser-use、Steel Browser OSS、Docling 和 `@react-pdf/renderer` 的软件许可费为 0。

首版不购买托管数据库、Temporal Cloud、Steel Cloud 或其他海外浏览器服务。实际成本来自国内云服务器、对象存储、网络和模型调用；使用 BYOK 时模型费用由对应用户账户承担。

### 10.2 Agno 可选商业服务

- 本地 AgentOS Control Plane：免费；
- Pro：$150/月，含一个线上连接和四个席位；
- 额外席位：$30/月；
- 额外线上连接：$95/月；
- Enterprise：询价，包含 Custom SSO/RBAC 和自托管 Control Plane 等能力。

CareerAct 首版不依赖这些服务。

### 10.3 assistant-ui 可选云服务

- Free：$0，含 200 MAU；
- Pro：$50/月，含 500 MAU；
- 超额：$0.10/MAU；
- Enterprise：询价。

CareerAct 自存会话，不依赖 assistant-ui Cloud。

### 10.4 Tiptap 可选云服务

- Start：$59/月，年付折算 $49/月；
- Team：$179/月，年付折算 $149/月；
- Business：$1,199/月，年付折算 $999/月。

CareerAct 首版只使用 OSS 编辑器。

### 10.5 Temporal

- Temporal OSS 自托管许可费：0；
- Temporal Cloud Essentials：至少 $100/月；
- Business：至少 $500/月；
- 超出套餐后 Actions 从 $50/百万次起；
- Active Storage：$0.042/GB·小时；
- Retained Storage：$0.00105/GB·小时。

本地开发采用 Dev Server；国内最小运营使用自托管 Temporal Server + PostgreSQL，不购买 Temporal Cloud。

### 10.6 Steel

- Launch：$0 月费 + 用量；
- 浏览器：$0.10/小时；
- 代理：$10/GB；
- CAPTCHA：$3/千次；
- 新账户一次性促销额度：$30，有效期 90 天；
- 托管代理或 CAPTCHA 需先充值至少 $10 解锁，充值余额可抵扣后续用量；
- 单会话最长 15 分钟；
- Scale：$250/月 + 用量；
- 浏览器：$0.08/小时；
- 代理：$6/GB；
- CAPTCHA：$1/千次；
- 每月额度：$100；
- 单会话最长 1 小时。

以上是可选海外托管服务的比较价格，不进入国内最小运营预算。Steel Browser OSS 自托管许可费为 0；并发、Files、Credentials、代理和验证码能力与 Cloud 的差异由 7.4 节所述方案处理。

### 10.7 Browser Use Cloud 备选

- 托管浏览器约 $0.02/小时；
- 住宅代理约 $5/GB；
- Dev：$29/月；
- Business：$299/月。

Cloud 属于商业托管能力，不等同于 browser-use MIT 开源库。

### 10.8 Hatchet 既有调研

- OSS 自托管许可费：0；
- Developer Cloud：$0，含每月前 100,000 次任务运行；
- Team：$500/月 + 用量；
- Scale：$1,000/月 + 用量；
- Enterprise：询价。

Hatchet 未作为最终主方案，保留价格用于未来比较。

### 10.9 LiteLLM

- LiteLLM OSS Core / Proxy 许可费为 0；
- LiteLLM Enterprise 按部署规模和使用量询价，没有统一固定公开价格；
- 模型 Token、Request 和供应商账户费用另行支付，不包含在 LiteLLM 软件费用中。

## 11. 主要官方依据

- [Next.js GitHub / MIT](https://github.com/vercel/next.js)
- [shadcn/ui GitHub / MIT](https://github.com/shadcn-ui/ui)
- [assistant-ui GitHub / MIT](https://github.com/assistant-ui/assistant-ui)
- [assistant-ui with-ag-ui](https://github.com/assistant-ui/assistant-ui/tree/main/examples/with-ag-ui)
- [assistant-ui AG-UI Runtime](https://www.assistant-ui.com/docs/runtimes/ag-ui/runtime-options)
- [assistant-ui Realtime Voice](https://www.assistant-ui.com/docs/guides/voice)
- [assistant-ui Pricing](https://www.assistant-ui.com/pricing)
- [Caddy GitHub / Apache-2.0](https://github.com/caddyserver/caddy)
- [AG-UI GitHub / MIT](https://github.com/ag-ui-protocol/ag-ui)
- [CopilotKit OSS 与 Enterprise 边界](https://docs.copilotkit.ai/agno/concepts/oss-vs-enterprise)
- [Tiptap GitHub / MIT](https://github.com/ueberdosis/tiptap)
- [Better Auth GitHub / MIT](https://github.com/better-auth/better-auth)
- [Docling GitHub / MIT](https://github.com/docling-project/docling)
- [`@react-pdf/renderer` GitHub / MIT](https://github.com/diegomura/react-pdf)
- [FastAPI GitHub / MIT](https://github.com/fastapi/fastapi)
- [Agno GitHub / Apache-2.0](https://github.com/agno-agi/agno)
- [Agno AG-UI Interface](https://docs.agno.com/agent-os/interfaces/ag-ui/introduction)
- [Agno Pricing](https://www.agno.com/pricing)
- [OpenHands Agent Canvas Architecture](https://docs.openhands.dev/openhands/usage/agent-canvas/architecture)
- [Better Auth JWT/JWKS](https://better-auth.com/docs/plugins/jwt)
- [Temporal Server GitHub / MIT](https://github.com/temporalio/temporal)
- [Temporal 自托管 Docker 部署](https://docs.temporal.io/self-hosted-guide/deployment)
- [Temporal Python SDK](https://github.com/temporalio/sdk-python)
- [Temporal Durable Timers](https://docs.temporal.io/develop/python/workflows/timers)
- [Temporal Cloud Pricing](https://docs.temporal.io/cloud/pricing)
- [Hatchet GitHub / MIT](https://github.com/hatchet-dev/hatchet)
- [Hatchet Durable Tasks](https://docs.hatchet.run/v1/durable-tasks)
- [Hatchet Rate Limits](https://docs.hatchet.run/home/features/rate-limits)
- [Hatchet Pricing](https://hatchet.run/pricing)
- [PostgreSQL License](https://www.postgresql.org/about/licence/)
- [PostgreSQL pg_trgm](https://www.postgresql.org/docs/current/pgtrgm.html)
- [Steel GitHub / Apache-2.0](https://github.com/steel-dev/steel-browser)
- [Steel Browser OSS Docker 自托管](https://docs.steel.dev/overview/self-hosting/docker)
- [Steel Local 与 Cloud 能力差异](https://docs.steel.dev/overview/self-hosting/steel-local-vs-steel-cloud)
- [Steel + browser-use Starter](https://github.com/steel-dev/steel-cookbook/tree/main/examples/steel-browser-use-starter)
- [Steel Sessions](https://docs.steel.dev/overview/sessions-api/overview)
- [Steel Live Sessions](https://docs.steel.dev/overview/sessions-api/embed-sessions/live-sessions)
- [Steel Pricing and Limits](https://docs.steel.dev/overview/pricinglimits)
- [browser-use GitHub / MIT](https://github.com/browser-use/browser-use)
- [browser-use Remote CDP](https://docs.browser-use.com/open-source/customize/browser/remote)
- [Browser Use Cloud Pricing](https://browser-use.com/pricing)
- [Playwright GitHub / Apache-2.0](https://github.com/microsoft/playwright)
- [Playwright 文件上传](https://playwright.dev/docs/input#upload-files)
- [LiteLLM 分区许可证](https://github.com/BerriAI/litellm/blob/main/LICENSE)
- [LiteLLM Realtime API](https://docs.litellm.ai/docs/realtime)
- [LiteLLM Realtime WebRTC](https://docs.litellm.ai/docs/proxy/realtime_webrtc)
- [阿里云 2026 年云服务器活动价格参考](https://developer.aliyun.com/article/1722603)
- [阿里云 OSS 存储计费](https://help.aliyun.com/zh/oss/storage-fees)
- [阿里云个人网站 ICP 备案](https://help.aliyun.com/zh/icp-filing/basic-icp-service/getting-started/quick-start-for-icp-filing-for-personal-websites)
- [Tiptap Pricing](https://tiptap.dev/pricing)
- [LobeHub Community License](https://github.com/lobehub/lobehub/blob/main/LICENSE)

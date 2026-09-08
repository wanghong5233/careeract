# CareerAct 技术架构与开源选型

> 文档类型：技术立项与架构决策  
> 项目名称：**CareerAct｜你的个人职业 Agent**  
> 对应产品文档：[PRD.md](./PRD.md)  
> 选型与成本依据：[TECHNICAL_SELECTION.md](./archive/TECHNICAL_SELECTION.md)  
> 状态：主架构、主选型与国内最小运营部署基线已确定  
> 核验日期：2026-09-07

## 1. 文档目的

本文独立保存已经完成的架构调研与选型，回答：

- 产品由哪些系统组成；
- 各层分别负责什么；
- 采用哪些开源组件；
- 哪些源码进入本项目并允许直接修改；
- 各组件如何共同实现 PRD。

本文只保留宏观架构、组件边界与最终决策，不展开候选比较、价格明细、接口和数据库表。候选调研、许可证与价格见选型文档。

## 2. 架构原则

### 2.1 产品拥有业务真相

职业档案、目标、岗位、材料版本、招聘沟通、申请记录和托管策略由本项目领域后端管理，不依赖 Agent Runtime 或聊天线程作为唯一存储。

Agent Runtime 的一次 Run 成功，不等于岗位申请或招聘沟通在业务上成功。外部结果必须根据真实页面、平台状态和结果证据确认。

### 2.2 复用底座，不重复造轮子

复用成熟开源项目提供的 Agent 循环、模型网关、UI 组件、编辑器和浏览器基础设施。本项目重点开发：

- 长期职业领域模型；
- 统一职业角色助手与职业项目管理；
- 职业规划与求职 Workflow；
- BOSS 直聘、猎聘与企业官网执行能力；
- 自动填表、投递、消息值班和信息整理；
- 公司调研、面经处理、刷题与面试训练；
- 授权策略、结果验证和用户报告。

### 2.3 关键源码可修改

关键上游项目不能作为不可调试的黑盒。Agno 与 browser-use 先 Fork，再将源码放入本项目 `vendor/`，固定版本并允许直接修改、断点调试和提交。assistant-ui 只作为 Agent 交互模块接入自有前端。

Playwright 等成熟基础依赖通过包管理器固定版本。Steel Browser OSS 固定版本并以 Docker 部署在国内云服务器；只有上游缺陷确实阻塞产品时才 Fork。Steel Cloud 是可选托管服务，不是首版运行依赖。

业务功能优先写在本项目代码中；只有 Runtime 或 browser-use 本身存在缺陷时，才修改 `vendor/` 中的源码。

### 2.4 产品报告与运维 Trace 分离

- 前端只提供用户需要的任务状态、结果报告、敏感操作记录和待处理事项；
- Agent 的逐步观察、内部判断、工具调用、性能和错误轨迹属于后端运维、排障与审计；
- 完整 Agent Trace 不作为前端产品对象。

### 2.5 敏感数据默认隔离

招聘平台登录态、BYOK、简历、沟通内容和浏览器画面均按高敏数据处理。认证、用户隔离、加密、短期访问凭证、撤销和删除能力属于首版基础架构，不是上线后的补充功能。

## 3. 总体架构

```text
用户浏览器
└── CareerAct Agent Workspace
      ├── Next.js + shadcn/ui
      ├── 职业项目、材料、岗位、申请、任务与报告
      ├── assistant-ui Agent 交互面板
      ├── 模拟面试（文字 / 实时语音）
      └── Tiptap
      │
      │ Better Auth Session / AG-UI / REST / WebRTC
      ▼
FastAPI 领域后端
├── 职业档案、目标与约束
├── 岗位、材料、沟通与申请
├── 授权、托管服务与结果报告
└── Agno AgentOS Runtime
      ├── LiteLLM 模型网关
      ├── 统一职业角色助手
      ├── 职业项目与领域工具
      └── Browser Service / Computer Use
            ├── Steel Browser OSS：隔离浏览器、Profile、实时画面与接管
            ├── Playwright：确定性操作与结果核验
            └── browser-use：未知页面的智能执行

基础设施
├── PostgreSQL
├── 国内对象存储
└── Temporal：持久任务、调度、重试、等待与恢复
```

### 3.1 Web 前端

`apps/web` 是基于 Next.js App Router 和 shadcn/ui 的自有 CareerAct Agent Workspace。产品围绕职业项目、材料、岗位、申请、任务、执行过程和结果组织，不围绕聊天线程组织。

assistant-ui 官方 `with-ag-ui` 示例作为 Agent 交互模块的代码起点，提供：

- assistant-ui 的 Thread、Message、Composer 与 Runtime Provider；
- `@assistant-ui/react-ag-ui` 对 AG-UI 流式事件、工具调用、取消和错误的适配；
- `RealtimeVoiceAdapter` 对实时双向语音、打断、转写和会话状态的适配；
- Tool Renderer 注册机制和基础会话交互。

Tiptap 用于结构化材料编辑，工具卡由 assistant-ui 与 shadcn/ui 组合实现。assistant-ui Cloud 不作为运行依赖，会话、消息、审批和任务历史保存在 CareerAct 后端。

负责用户直接使用的职业工作台：

- 职业档案、目标、约束与能力账本；
- 职业项目、任务、里程碑与准备训练；
- 岗位、材料版本、招聘沟通和申请流程；
- Agent 对话与任务入口；
- 文档编辑、Diff 和必要审批；
- 远程浏览器画面及人工接管；
- 托管服务启停、授权设置、结果报告和待办。

前端不保存业务唯一真相，也不承担 Agent 长期运行。

正式审批和待处理事项使用 CareerAct 后端对象，不依赖 assistant-ui 仍处于实验状态的 AG-UI Interrupt 或线程 API。

### 3.2 领域后端

采用 FastAPI，由本项目开发，是业务真相来源：

- 用户身份和数据权限；
- 职业领域对象及相互关系；
- 材料版本、重复申请和状态历史；
- 托管授权与长期业务状态；
- 对 Agent、模型和浏览器能力的统一调用；
- 对招聘邮件、通知、外部搜索和材料转换的适配；
- 外部动作的业务验收和结果回写。

首版将领域后端和 AgentOS 放在同一个 FastAPI 服务中，避免过早拆成两个部署单元。

Web 身份由 Better Auth 管理。浏览器只访问同源 Next.js BFF；BFF 验证 Session Cookie，通过 Better Auth JWT Plugin 获取短期 Token 后转发给 FastAPI / AG-UI。FastAPI 与 AgentOS 按 issuer、audience、过期时间和 JWKS 验证 Token，并以 `sub` 作为统一用户 ID。

### 3.3 Agent Runtime

采用 Agno AgentOS v3，运行在服务器端 Python / FastAPI 进程中。

负责：

- Agent 与工具调用循环；
- Agent 内部的推理与工具 Workflow；
- Run / Session；
- 暂停、恢复和 HITL；
- 面向交互式 Agent 的 AG-UI Interface；
- 面向长期任务与领域数据的 REST 接口；
- Runtime Trace 和技术执行状态。

AgentOS 不提供职业产品前端、职业领域模型或完整 Computer Use。

AG-UI 只负责 Agent 与前端之间的交互事件，不替代领域 API，也不成为申请、材料和托管任务的业务状态源。

AgentOS 的后台 Run 不作为跨系统业务流程的唯一持久任务保证。跨 Agent、浏览器、通知渠道和长时间用户等待的托管任务由 Temporal 编排，Agno Run 作为其中一个可重试、可验收的智能执行步骤。

### 3.4 统一职业角色助手与模型适配

产品需要的是一个长期理解用户生涯背景、能回答职业问题并调用工具执行的统一角色助手。“微调”是可能采用的模型优化手段，不等于这项产品需求本身。

模型适配分阶段进行：

1. **首版角色基线**：使用结构化职业档案、目标、约束、历史决策、角色指令和领域工具建立稳定上下文；
2. **评测与数据积累**：针对方向判断、岗位分析、材料修改、公司调研、面试准备和工具调用建立评测集，识别仅靠上下文无法解决的问题；
3. **领域微调**：积累足够且获得授权的高质量数据后，再评估对模型进行监督微调或偏好优化，以改善职业角色一致性、领域判断和工具选择；
4. **个性化保持外置**：用户个人事实、目标和敏感职业历史保存在领域数据库中，不直接写进共享模型权重，避免信息过期、难以删除和隐私泄露。

首版不把微调作为上线前提。没有评测数据时直接微调，无法证明效果，也会把用户经常变化的个人背景固化进模型。微调主要解决共性的职业角色能力，个人化由实时职业档案提供。

用户可以通过 LiteLLM 接入平台模型或 BYOK 模型。无论底层调用哪一个模型，前端始终呈现同一个 CareerAct 角色，并继承同一份职业上下文。

模拟面试复用同一套职业上下文和模型网关，不建立第二套 Agent Runtime：

- 文字模拟面试通过 assistant-ui、AG-UI 和 Agno 运行；
- 实时语音模拟面试由领域后端根据实际投递材料、JD、公司信息和面经创建面试会话，Next.js BFF 从 LiteLLM 获取短期 Realtime 凭证，浏览器通过 assistant-ui `RealtimeVoiceAdapter` 和 WebRTC 连接受支持的实时语音模型；
- 面试转写、问题、回答、评价和薄弱项回写领域后端，继续生成准备任务；
- AG-UI 负责文字 Agent 事件，不承载实时音频；实时语音是一条独立传输通道，但继续使用相同的身份、职业数据和模型网关。

该链路使用已经选定的 assistant-ui、LiteLLM、Next.js 和领域后端，不增加新的基础框架。首版可以只实现文字交互，后续启用实时语音而不改变系统分层。

### 3.5 模型网关

采用 LiteLLM OSS Proxy，负责：

- 统一模型 API；
- 多供应商路由；
- 虚拟 Key；
- 预算与用量；
- 模型供应商隔离。

LiteLLM 是后端模型网关，不保存职业业务状态。

### 3.6 材料处理

- **Tiptap**：结构化材料编辑和交互式修改；
- **Docling**：解析 PDF、DOCX 等原始材料并提取结构；
- **`@react-pdf/renderer`**：生成首版 PDF 简历与报告；
- **领域后端与对象存储**：管理事实来源、版本、Diff、审批、回滚和原始文件。

### 3.7 Browser Service / Computer Use

Computer Use 采用已经存在官方集成的三层组合，不依赖修改 AgentOS 循环实现：

1. **Steel Browser OSS**：自托管浏览器基础设施。负责隔离 Chromium、用户与站点 Profile、持久登录态、远程 CDP、实时画面、人工接管和会话生命周期；
2. **Playwright**：默认确定性执行器。负责已知页面和站点适配器中的定位、表单、日期、下拉、附件、等待、保存后读回和结果核验；
3. **browser-use OSS**：智能执行器。仅在页面未知、结构变化或确定性定位失效时，负责语义/视觉理解、页面探索和候选动作。

Steel 本身不理解岗位和表单，也不会自主完成申请；browser-use OSS 本身不提供成熟的多租户浏览器基础设施；Playwright 不具备 Agent 决策。三者职责互补。

首版部署策略：

- 本地开发和国内最小运营都使用 Steel Browser OSS；
- 最小运营实例同时只运行一个浏览器会话，其他任务排队，不删减 Profile、实时画面、人工接管或自动操作能力；
- `.cache` 与 Profile 目录挂载持久卷；Steel API 和 CDP 只在 Docker 内网开放，实时接管由 CareerAct 同源服务代理；
- Steel Cloud 或其他托管浏览器只作为扩容备选，不是运行依赖；
- browser-use 通过 Steel 官方支持的远程 CDP 接入同一浏览器会话。

同一会话只允许一个写入方：Playwright、browser-use 和人工接管之间通过 Session Lease 互斥。进入人工接管时必须暂停 Agent；browser-use 返回成功后，仍由确定性读取或站点适配器验收真实结果。

站点适配器、授权、重复投递、保存后验收和业务状态回写属于 CareerAct，不下放给 browser-use 的 Prompt。

需要登录、验证码或人工输入时立即通知用户并暂停 Agent，浏览器会话由 CareerAct 按资源上限设置超时。超时后保存证据、释放浏览器并把任务标为待处理。确认未发生外部写操作时才从业务 Checkpoint 重跑；提交或发送结果不确定时转人工对账，不承诺恢复未保存的页面 DOM。

### 3.8 数据与持久任务

- **PostgreSQL**：保存用户、职业领域对象、授权、任务和状态历史；
- **对象存储**：保存原始材料、简历、附件、截图和结果证据；
- **Temporal OSS**：持久任务、定时调度、重试、长时间等待、事件唤醒和恢复；
- **Temporal Worker**：执行 Activity，调用 Agno Run、Browser Service 或外部渠道，并把结果回写领域后端。

本地开发使用 Temporal CLI Dev Server；国内最小运营使用官方 `temporalio/server` 镜像与 PostgreSQL 持久化，不使用只面向开发测试的 `start-dev`。Temporal Cloud 是可选托管服务，不是首版运行依赖。

CareerAct PostgreSQL 是业务真相；Temporal Event History 是执行恢复依据。招聘网站无法接收客户端幂等键，因此结果不确定的提交或消息发送禁止自动重试，必须先读取外部状态或转人工对账。

无人值守托管由 Temporal 定时或事件触发，不是让一次模型调用或浏览器会话连续运行数天。

### 3.9 身份、密钥与数据安全

- **身份认证**：Better Auth OSS；Web 使用 Session Cookie，Next.js BFF 换取短期 JWT，FastAPI / AgentOS 使用 JWKS 验证；
- **用户隔离**：数据库查询、对象存储 Key、Temporal Workflow、Steel Profile、浏览器会话和 Trace 均绑定统一 `user_id`；
- **密钥保护**：BYOK 和其他应用密钥使用信封加密，主密钥只存放在部署环境的 Secret Manager，不与密文同库存放；
- **登录态**：优先让用户在隔离浏览器中直接登录并保存 Profile，不采集招聘平台明文密码；
- **文件访问**：对象存储默认私有，只签发短时、最小范围 URL；
- **浏览器接管**：直播与接管链接短时有效，不写入公开日志；
- **撤销与删除**：用户可以关闭托管、撤销授权、删除 Profile、BYOK、材料和账户数据；备份按保留策略到期清除。

### 3.10 PRD 能力映射

- 职业档案、职业项目、岗位、材料和申请流程：Agent Workspace + FastAPI 领域后端 + PostgreSQL；
- 统一职业 Agent：assistant-ui + AG-UI + Agno + LiteLLM；
- 模拟面试：职业档案与实投材料 + Agno 文字交互 / LiteLLM Realtime 语音交互 + assistant-ui；
- 材料编辑、版本和证据：Tiptap + 领域版本模型 + 对象存储；
- 岗位发现、网申、平台沟通和结果核验：Temporal + Browser Service；
- 后台续跑与无人值守托管：Temporal 持久任务 + 授权策略 + 执行账本；
- 招聘邮件、通知和公司调研：领域连接器调用官方 API、模型搜索能力或 Browser Service；
- 结果报告与敏感操作记录：领域后端 + PostgreSQL + 对象存储。

## 4. 已确定的开源选型

### 4.1 前端

- **Next.js**：CareerAct Agent Workspace 的应用框架、路由和服务端能力；
- **Better Auth**：Session、JWT / JWKS 与账户认证；
- **shadcn/ui**：基础 UI，组件源码复制进项目后直接修改；
- **assistant-ui**：嵌入工作台的 Agent 对话、流式消息和工具结果模块；不依赖 assistant-ui Cloud；
- **Tiptap Core / 开源 UI Components**：结构化材料与简历编辑；
- **Docling**：PDF、DOCX 等材料解析与结构化提取；
- **`@react-pdf/renderer`**：PDF 简历与报告生成。

主接入协议为 Agno AgentOS v3 原生 AG-UI。职业业务状态、正式审批和会话持久化继续由 CareerAct 后端负责。

### 4.2 后端

- **Caddy**：国内单机部署的 HTTPS 与同源反向代理；
- **FastAPI**：领域后端和 AgentOS 宿主；
- **Agno AgentOS v3**：选定的 Agent Runtime；
- **AG-UI**：交互式 Agent 的前后端协议；
- **Temporal OSS**：持久任务、调度、等待、重试和恢复；
- **LiteLLM OSS Proxy**：模型网关；
- **PostgreSQL**：主数据库；
- **对象存储**：材料和证据文件。

### 4.3 Browser Service / Computer Use

- **Steel Browser OSS**：国内自托管浏览器会话、Profile、CDP、实时画面与人工接管；
- **Playwright**：确定性操作、站点适配与最终核验；
- **browser-use OSS**：页面变化和未知结构下的智能 Computer Use；
- **CareerAct Browser Service**：封装三者，提供租约、授权、幂等、证据和业务结果。

### 4.4 选型结论

当前方案不是从零开发：前端复用成熟 UI 与编辑器，材料层复用 Docling 和 React PDF，Agent 后端复用 Agno，模型层复用 LiteLLM，持久任务复用 Temporal，浏览器层复用 Steel、Playwright 和 browser-use。本项目只开发不可外包的职业领域产品、站点流程与业务可靠性。

不采用 LobeHub、OpenHands、CopilotKit、Hatchet 等候选的原因、社区规模、许可证和成本依据见：[TECHNICAL_SELECTION.md](./archive/TECHNICAL_SELECTION.md)。

## 5. 代码归属与仓库边界

项目仓库使用 `careeract` 作为工作名：

```text
careeract/
├── apps/web/                  # CareerAct Agent Workspace + assistant-ui 模块
├── services/api/              # FastAPI 领域后端 + AgentOS
│   ├── domain/                # 职业领域对象
│   ├── tools/                 # 领域与浏览器工具
│   ├── integrations/          # 邮件、通知、搜索与材料转换
│   └── routes/                # REST 与 AG-UI 接口
├── services/worker/           # Temporal Worker
│   ├── workflows/             # 持久职业与求职 Workflow
│   └── activities/            # Agent、浏览器与外部写操作
├── services/browser/          # Steel / Playwright / browser-use 编排
│   ├── sessions/              # Profile、Session Lease 与人工接管
│   ├── playwright/            # 确定性操作和结果核验
│   ├── computer_use/          # browser-use 受控智能执行
│   └── site_adapters/         # BOSS、猎聘和企业官网
├── vendor/
│   ├── agno/                  # Fork 的 Agno 源码
│   └── browser-use/           # Fork 的 browser-use 源码
├── docker-compose.yml
└── pyproject.toml
```

修改位置遵循：

- 职业档案、岗位、材料、申请和沟通：`services/api/domain/`；
- 求职流程、托管策略和审批关口：`services/worker/workflows/`；
- Agno Run、浏览器操作和外部写入：`services/worker/activities/`；
- 招聘邮件、通知、搜索和材料转换：`services/api/integrations/`；
- 填表、日期、附件、消息和站点适配：`services/browser/`；
- checkpoint、HITL、Runtime 事件或用户隔离缺陷：`vendor/agno/`；
- 智能浏览器执行器本身的缺陷：`vendor/browser-use/`；
- Steel Browser OSS 默认通过固定版本镜像使用；上游缺陷确实阻塞时再 Fork，商业 Cloud 不作为首版依赖。

`vendor/` 中的改动单独提交并说明原因；可以贡献上游的修复优先提交 PR，避免长期维护大量私有补丁。

## 6. 许可证与商业边界

- 主选组件采用 MIT 或 Apache-2.0，允许修改、私有部署和商业运营；
- PostgreSQL 使用 PostgreSQL License；对象存储许可证取决于最终实现；
- LiteLLM 只使用 MIT 范围，不启用 `enterprise/` 商业许可功能；
- 当前开源范围不要求支付商业许可费或收入分成；
- 项目必须保留适用的版权、LICENSE 和 NOTICE。

## 7. 价格与成本边界

- 自托管开源组件许可费为 0；
- 首版不依赖 Agno、assistant-ui、Tiptap 或 Temporal 的付费云服务；
- 浏览器基础设施使用国内自托管 Steel Browser OSS，不产生按小时的软件费用；
- 主要运行成本来自国内云服务器、对象存储、网络和模型 API；
- 完整价格、免费额度和商业服务边界见：[TECHNICAL_SELECTION.md](./archive/TECHNICAL_SELECTION.md)。

## 8. 部署基线

国内最小运营使用一台 Linux 云服务器，建议配置为 4 核 CPU、16GB 内存和至少 80GB SSD。所有常驻服务通过 Docker Compose 部署在同一台主机；对象文件使用同地域的国内对象存储，不在主机内运行 MinIO：

```text
Docker Compose
├── caddy       HTTPS 与同源反向代理
├── web         CareerAct Agent Workspace + Better Auth + assistant-ui 模块
├── api         FastAPI + 领域后端 + Agno AgentOS
├── worker      Temporal Worker
├── browser     Playwright + browser-use 编排服务
├── steel       Steel Browser OSS + Chromium + 持久 Profile
├── temporal    Temporal Server 正式镜像
├── litellm     模型网关
└── postgres    业务、Agent、LiteLLM 与 Temporal 使用独立数据库或 Schema

同地域国内云服务
└── OSS / COS / TOS：材料、附件、截图、备份和结果证据

模型供应商
└── LiteLLM 接入国内可用模型或用户 BYOK
```

最小运营限制 LiteLLM 为单 Worker、Steel 为单浏览器会话、Docling 为单解析任务；超出的任务进入队列。该限制降低并发，不删除产品能力。PostgreSQL 每日备份到对象存储，Docker 镜像和依赖预先同步到国内镜像仓库，避免运行时依赖 GitHub、Docker Hub 或国外托管服务。

本地开发时，自研代码和 `vendor/` 源码挂载进容器，支持热重载和断点调试。Agno 不是独立的不可修改成品服务，而是嵌入本项目后端的源码级 Runtime。

## 9. 相关文档

- 产品需求：[PRD.md](./PRD.md)
- 开源选型、候选比较、许可证、价格与官方依据：[TECHNICAL_SELECTION.md](./archive/TECHNICAL_SELECTION.md)

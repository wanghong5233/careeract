# BOSS 招聘沟通实施方案

状态：方案冻结前的实施计划（2026-10-07）。本专题用于把 PRD 中的“招聘平台沟通”具体化；还没有开放真实 BOSS 写操作，也不把历史 Pulse 的实现当作 CareerAct 的代码依赖。

## 1. 问题和首个结果

当前目标不是做一个通用网页 Agent，而是让职业 Agent 在 BOSS 直聘上完成一条可追溯的真实闭环：

```text
指定岗位/岗位列表
  → 读取岗位与招聘方会话
  → 按职业目标、硬约束和已确认事实判断
  → 生成带依据的个性化打招呼草稿
  → 受限授权
  → BOSS 页面发送
  → 页面状态核验
  → 成功/失败/未知结果报告
```

首个可验收目标是单用户、单 BOSS Profile、单岗位或小批量岗位、首次打招呼。它要证明的是业务闭环和可靠性，不是“任意页面都能自动操作”。

首版明确不包含：HR 后续自动回复、简历卡发送、全网岗位巡检、长期无人值班、逆向 BOSS 私有 API、绕过验证码/风控，以及没有结果证据的“成功”提示。

## 2. 已知证据和仍需复验的事实

### 2.1 当前仓库的确定事实

- PRD 已将 BOSS 主动沟通列为正式能力，要求保存沟通内容、发送依据和处理结果。
- CareerAct 已有 Agno AgentOS/AG-UI 文本 Runtime、职业上下文工具、PostgreSQL 领域状态、Temporal 基础 Workflow 和 Browser Service 的会话租约边界。
- Browser Service 当前只有底座和内部控制契约，站点适配器、业务授权用例、沟通领域对象和生产执行入口尚未接入。
- 浏览器执行必须通过 CareerAct 的用户归属、任务、授权、尝试和请求标识；原始 CDP/调试地址不能交给 Web 客户端。

### 2.2 历史 Pulse 的可复用教训

历史 Pulse 在 2026-03 对 BOSS 做过真实页面诊断和沟通执行，形成了以下证据。它们是待在当前环境复验的输入，不是可以直接复制的依赖：

1. 标准 Playwright/Puppeteer 的 CDP 连接曾触发 BOSS 的协议级检测，页面跳转到 `about:blank`；JS stealth、真实 Chrome UA 和拦截 `location` 都没有解决。
2. Pulse 通过 `patchright` 和长驻浏览器会话池恢复了登录、搜索、消息和职位详情页面；每次请求启动/关闭浏览器会导致会话失效风险。
3. BOSS 是 SPA：`goto` 返回不代表认证完成，必须等待异步路由稳定并持续检查登录/风控 URL。
4. 页面流程大多是确定性的：搜索列表、会话列表、职位详情、输入框和发送按钮应由站点适配器执行；视觉模型不应承担普通导航决策。
5. 页面细节不能靠猜：例如“查看职位”曾是 `span` 而非 `a`，公司/岗位字段没有稳定 class；应先采集 DOM 合同，再维护多候选选择器和 fail-loud 诊断。
6. BOSS 自带“立即沟通”可能已经发送预设招呼，额外输入一条会造成重复消息；执行前必须确认平台动作语义。
7. 外部写操作不能按 HTTP 超时自动重试；点击返回不代表平台已发送，未知结果必须进入对账或人工处理。

这些结论需要用当前 BOSS 页面和当前 patchright 版本做一次无写入 canary。历史材料不能证明今天仍然可登录或长期可用。

2026-10-07 的只读当前环境探测打开 `https://www.zhipin.com/web/geek/jobs` 后先显示“加载中，请稍候”，随后浏览器标题和 URL 变为 `about:blank`。这与历史反爬现象相符，但当前 Web 只是 Codex 的受控浏览器，不能单独证明 patchright、真实 Chrome 或用户账号的结果；它把 Phase 0 标记为“需要专用驱动实验”，没有进行登录或写操作。当前 `services/browser` 仍依赖标准 `playwright`，尚未引入 patchright。

## 3. 架构判断

### 3.1 Agno、Runtime、Harness 的分工

这里使用的是 **Agno**，不是“ango”。不引入 Zcode/Codex Harness 作为运行时替换：

| 层 | CareerAct 采用 | 负责什么 | 不负责什么 |
| --- | --- | --- | --- |
| Agent 决策循环 | Agno AgentOS + 现有 Runtime | 上下文、模型调用、工具选择、结构化判断和草稿生成 | 不能决定外部发送已成功，不能替代业务状态 |
| 交互协议 | AG-UI | 把 Agent 进度和结果呈现给 Web | 不保存岗位、授权或发送结果 |
| 业务持久化 | FastAPI application/domain + PostgreSQL | 岗位、会话、草稿、授权、尝试、证据和状态历史 | 不依赖聊天消息作为事实源 |
| 长任务编排 | Temporal Workflow | accepted/running/waiting/failed/timed_out/cancelled/completed、信号、checkpoint | Workflow 本身不做网络、数据库或浏览器 I/O |
| 外部执行 | Worker Activity + Browser Service | 调用浏览器、租约、站点适配和页面核验 | 不让模型直接拿 CDP 或自由点击 |
| 执行 Harness | CareerAct 的工具契约、策略门、租约、幂等和回执组合 | 将模型意图变成受控的一次执行，并绑定观测、尝试和结果 | 不需要复制一个通用 Coding Harness |

Agno 可以很好复用现有对话和职业上下文；真正缺少的是招聘业务的状态、授权和外部写入语义。这个缺口用 CareerAct 的领域层、Temporal 和 Browser Service 补齐，而不是换掉 Agno。

### 3.2 为什么当前不引入 Zcode/Codex Harness

历史 Harness 研究适合帮助我们理解 loop、工具、审批、checkpoint、回放和多 Surface 边界，但它们主要面向 Coding Agent 或通用个人助手。当前任务已经有 Agno AgentOS、AG-UI、Temporal、Browser Service 和业务领域边界；引入新的 Harness 会增加状态、工具协议和恢复语义的重复实现。

只有在后续出现可复用缺口时才重新评估，例如：需要跨多个职业执行器共享统一 tool-call journal、暂停/恢复协议或离线轨迹回放，并且现有组合无法以局部适配解决。评估必须以一个具体失败样本为依据，不以“框架更成熟”作为理由。

### 3.3 DOM、Accessibility Tree 和视觉的选择

执行顺序固定为：

1. **DOM/Playwright 站点适配器**：已知 BOSS 页面使用多候选 selector、文本/ARIA 锚点、显式等待和页面状态合同。
2. **Accessibility Tree 或结构化文本**：只用于诊断、候选元素确认或页面改版后的低风险探索，不直接授权发送。
3. **视觉/browser-use**：仅用于未知结构、适配器失效后的候选动作或人工接管辅助；候选动作必须回到确定性核验，不能直接宣布完成。

视觉方案不作为首版主路径，原因是消息发送不可逆、BOSS 流程已知、视觉点击成本和误触风险更高。任何写操作都需要发送前状态确认和发送后页面回读。

## 4. 领域状态和执行状态

PostgreSQL 是业务真相，建议首个增量引入以下对象；具体字段在编码前以迁移和 API 契约冻结：

| 对象 | 关键内容 | 状态示例 |
| --- | --- | --- |
| `JobOpportunity` | 平台、岗位/公司/地点/薪资、来源 URL、页面快照版本、匹配判断 | `observed` / `matched` / `rejected` / `needs_review` |
| `RecruitingConversation` | BOSS 会话标识、岗位关联、招聘方摘要、最后读取时间 | `observed` / `needs_reply` / `contacted` / `blocked` |
| `OutreachDraft` | 消息正文、引用事实、岗位依据、生成 Run、版本 | `draft` / `approved` / `sent` / `superseded` |
| `ExternalAuthorization` | 用户、平台、岗位范围、允许动作、数量/频率、材料范围、有效期、撤销时间 | `pending` / `active` / `revoked` / `expired` |
| `CommunicationAttempt` | 授权、任务/尝试 ID、幂等键、页面阶段、证据摘要、错误分类 | `accepted` / `running` / `waiting` / `failed` / `unknown` / `completed` |

`CommunicationAttempt` 和 Agent Run 分开：Agent Run 完成只说明判断或草稿完成，不能代表 BOSS 已发送。`unknown` 是终态业务结果之一，不能自动转换为 `failed` 或 `completed`。

## 5. 实施阶段和验收门槛

### Phase 0：可行性 canary（先做）

- 在隔离合成 Profile 中验证 patchright/当前浏览器版本能打开 BOSS 登录、搜索、消息和职位详情页面。
- 记录 `about:blank`、登录重定向、风控页、验证码、SPA 稳定时间、页面结构和浏览器内存。
- 不发送消息、不读取真实简历；失败就停止并记录阻塞原因，不用 stealth 或逆向 API 反复试错。

**通过条件：** 当前环境可稳定停留在登录/公开页面；知道需要用户人工登录的边界；确定 Browser Service 应采用的驱动和 Profile 生命周期。

### Phase 1：只读 BOSS 适配器

- 岗位搜索/岗位详情/会话列表/会话详情读取。
- 登录、验证码、风控、空页面、改版和 SPA 未稳定的明确结果。
- DOM 合同、selector 降级、页面诊断和合成 Fixture 测试。

**通过条件：** 对指定岗位能拿到结构化摘要和来源证据；页面不匹配时返回 `needs_review`，不伪造岗位或 HR 信息。

### Phase 2：匹配和草稿

- Agno 工具只读取已授权职业上下文、岗位对象和历史沟通。
- 输出严格 Schema：匹配结论、证据引用、未知项、打招呼草稿和不发送理由。
- 草稿持久化并支持用户修改/批准；事实不足时只生成待核实状态。

**通过条件：** 同一岗位重复运行不会生成重复沟通任务；草稿只能引用可追溯事实；模型异常不改变岗位或授权状态。

### Phase 3：受限发送和核验

- 用户显式开启仅限 BOSS 打招呼的短时授权：岗位范围、数量上限、频率、有效期和撤销。
- Temporal Workflow 负责状态和 checkpoint；Activity 获取 Browser lease，调用 BOSS 适配器完成一次发送。
- 发送前确认会话/岗位/草稿版本和幂等键；发送后读取会话列表/详情确认消息内容或平台回执。
- 网络超时、页面跳转、回读失败和租约断开进入 `unknown`，先人工对账，禁止自动重发。

**通过条件：** 合成页面成功、拒绝、验证码、风控、重复会话、未知结果和取消路径都有可核验记录；报告显示动作、依据、材料/授权版本和下一步。

### Phase 4：真实单岗位验收

- 用户在可见隔离浏览器中人工完成登录，确认 Profile 和目标岗位。
- 先运行只读和草稿路径，再由用户开启本次授权；首个真实发送由用户在场观察。
- 记录 BOSS 当前行为、耗时、风控反馈和结果证据，随后决定是否扩大到小批量。

### Phase 5：小批量和托管（后续）

- 小批量涓流发送、日/时段上限和暂停开关。
- 未读消息整理、常规问题回复和简历卡发送分别设计、分别授权、分别验收。
- 定时托管必须建立在真实单岗位路径稳定、撤销和未知结果对账已通过之后。

## 6. 需要先回答的工程问题

1. 当前 BOSS 版本是否仍检测标准 CDP；patchright 依赖是否能在现有 Browser 镜像和 Windows 开发环境固定安装。
2. Steel/Browser Service 如何承载 patchright 的持久 Profile、可见接管和单写者租约；不能把 Pulse 的进程内单例直接当成多用户方案。
3. BOSS 的“立即沟通”是平台预设招呼还是打开会话；必须在执行前读取页面语义，避免重复发送。
4. 发送后可用什么确定性信号证明消息已出现；仅点击按钮、HTTP 200、截图变化都不够。
5. 领域授权、任务状态和浏览器授权如何绑定；用户撤销后未执行任务如何停止，租约失效如何进入人工处理。
6. 当前 Agno 工具调用如何把结构化回执、岗位版本、授权 ID 和尝试 ID 传给业务层；不把这些字段塞进自由文本。

## 7. 复用和不复用

**直接复用：** CareerAct 的 Agno AgentOS/AG-UI、职业上下文工具、PostgreSQL 归属与版本模式、Temporal 状态模型、Browser lease/签名控制、现有测试和端口/开发流程。

**借鉴但重新实现：** Pulse 的 BOSS DOM 合同、SPA 稳定等待、patchright 可行性结论、常驻 Profile 思路、发送后回读、未知结果和变更操作不重试、Action Report 与回归测试结构。

**不复用：** Pulse 的领域模型、MCP 网关、进程内全局状态、旧 scheduler、私有 API 逆向、默认自动回复/发简历策略，以及任何绕过平台风控的脚本。

## 8. 交付产物

- 本专题：方案、决策、风险和验收证据的唯一入口。
- Phase 0：浏览器可行性实验记录，不修改产品状态。
- Phase 1：BOSS 站点适配器和合成 Fixture。
- Phase 2：岗位/沟通/草稿领域对象、Agent 工具和 Web 结果卡。
- Phase 3：授权、Temporal Workflow、浏览器 Activity、发送核验和报告。
- 每阶段完成后更新 `STATUS`；未通过的浏览器开放门槛继续保持控制入口关闭。

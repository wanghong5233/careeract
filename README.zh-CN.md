# CareerAct

**你的个人职业 Agent。**

[English](README.md) | 简体中文

**规划职业，并把下一步真正做完。**

CareerAct 是一个开源的 Agent-native 产品，旨在把求职与职业发展作为持续项目来管理。
它将职业目标、个人经历、机会、申请与准备连接起来，让一个了解你的职业 Agent 持续参与
这段历程。

你确定方向、提供反馈、做出决定；Agent 关联背景、组织工作、创作材料，并在授权范围内
执行任务。从第一次求职，到转岗选择，再到入职后的成长，产品围绕同一份职业背景展开。

## 为什么做 CareerAct

职业事务分散在不同地方：目标写在笔记里，经历保存在简历文件里，申请记在表格里，
招聘沟通留在各个平台。AI 可以帮你改一份材料，但解释背景、衔接下一步、回头找记录，
依然需要自己完成。

CareerAct 的核心思路是：**把每个职业阶段组织成一个项目，由 Agent 持续推进。**
一个岗位关联选择它的理由、实际投出的材料、招聘沟通与面试准备；新的经历和关键决策
继续沉淀，成为下一个职业项目的背景。

## Agent-native 的协作方式

- **围绕目标组织工作。** 一次校招、一次转岗或一项能力提升计划，各有目标、约束、
  任务和里程碑，共享持续积累的个人职业档案。
- **由 Agent 主导推进。** 自然语言委托是起点，Agent 选择上下文、产出成果、协调行动；
  文档、对比和浏览器等工作面随具体任务展开。
- **在成果上持续协作。** 查看改稿差异与来源，提供反馈，继续完善同一份有版本的材料。
  已确认的经历事实与对外表达分别管理。
- **执行有明确边界。** 每次行动关联具体岗位、材料版本和授权，并依据外部真实状态
  核验结果。事实确认、对外承诺与关键职业选择由用户掌握。
- **每一步留下可复用的积累。** 申请记录、面试反馈、项目证据和入职后的经历，继续服务
  下一次准备与判断。

## 贯通职业全过程

产品设计将六类职业工作连接起来：

| 领域 | 解决的问题 |
| --- | --- |
| 职业规划与项目 | 将阶段目标转化为优先级、任务、里程碑、准备计划与复盘 |
| 职业档案与能力证据 | 持续维护经历、技能、成果、约束，以及支撑它们的真实依据 |
| 机会发现与岗位判断 | 从官方招聘源和平台发现岗位，核对匹配度、资格、截止时间与申请限制 |
| 材料准备与求职申请 | 形成岗位定向材料，保留实投版本，衔接填表、投递与流程跟进 |
| 招聘沟通与面试准备 | 将招聘方会话、公司调研、面经、训练与 Offer 比较关联到具体岗位 |
| 持续委托 | 为盯岗、消息处理和通知整理设定有限职责，支持暂停与撤销 |

企业官网及官方招聘源提供一手岗位信息与申请入口，BOSS 直聘、猎聘等平台补充机会
和招聘方沟通。

### 从目标到职业记录

一句“帮我推进适合我背景的 AI 工程岗位求职”，连接的是一整段工作：

1. 明确项目方向、硬约束与相关经历。
2. 发现机会，说明选择或跳过某个岗位的依据。
3. 形成待审阅材料，保留每次申请实际使用的版本。
4. 在授权范围内完成沟通与申请，并核验外部结果。
5. 围绕具体岗位和实投材料组织跟进与面试准备。
6. 保存反馈与决定，调整下一步行动。

同样的项目结构也适用于学习计划、作品积累和职业转型。一次求职结束后，新工作中的
经历继续进入个人职业历史。

## 技术架构

架构将职业记录、Agent 推理与任务执行分开。PostgreSQL 保存业务状态，Agent Run、
对话历史与浏览器会话引用这些记录。

| 层次 | 架构设计 |
| --- | --- |
| Agent 交互 | Next.js、React、assistant-ui、AG-UI 与 shadcn/ui |
| 身份与领域服务 | Better Auth、同源 BFF 与 FastAPI |
| Agent Runtime 与模型 | Agno AgentOS 与 LiteLLM |
| 职业记录 | PostgreSQL 与版本化领域对象 |
| 持久任务编排 | Temporal Workflow 与 Activity |
| 浏览器执行 | Steel 会话、Playwright 站点适配，以及应对变化或未知页面的 browser-use |

CareerAct 自行管理职业语义、授权策略和结果核验，成熟开源组件提供底层 Runtime
与基础设施。项目维护的 Agno、browser-use Fork 通过 `git subtree` 固定在 `vendor/`。

## 本地运行

环境要求：Windows 或 Linux、Python 3.11–3.13、Node.js 22、`uv`、npm，以及带 Compose
的 Docker。以下命令从仓库根目录运行：

```powershell
uv sync --frozen --all-packages --group dev
npm --prefix apps/web ci
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
if (-not (Test-Path apps/web/.env.local)) { Copy-Item apps/web/.env.example apps/web/.env.local }
```

按[开发指南](docs/handbook/DEVELOPMENT.md#配置与启动)配置数据库、认证和模型凭据，
然后启动 PostgreSQL：

```powershell
docker compose up -d postgres
```

等待 PostgreSQL healthy 后：

```powershell
uv run --package careeract-api alembic -c services/api/alembic.ini upgrade head
docker compose up -d litellm
```

等待 LiteLLM 就绪后：

```powershell
uv run --no-sync python scripts/manage_model_key.py provision
npm --prefix apps/web run dev
```

打开启动器打印的地址。服务配置、检查与排障见[开发指南](docs/handbook/DEVELOPMENT.md)，
工程约定见[贡献者说明](AGENTS.md)。

## 许可证

CareerAct 自有源码采用 [Apache License 2.0](LICENSE)，归属与第三方声明见
[NOTICE](NOTICE)。vendor 项目与依赖保留各自许可证。

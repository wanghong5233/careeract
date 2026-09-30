# 单人工程管理：调研依据与取舍

阅读日期：2026-09-29–30。以下结论来自实际读取的上游正文和独立分析；这里保留摘要，
不复制上游规则、模板或脚本。仓库 main 和在线文档会演进，本地流程不会自动跟随更新。

## 文档工程与敏捷管理

这些方法分别解决知识组织、版本维护、工作流和 AI 协作问题，没有任何一个直接规定
CareerAct 的目录。handbook/topics 是结合本项目体量的适配，不宣称行业统一标准。

| 来源 | 正文支持的经验 | 本项目采用与边界 |
| --- | --- | --- |
| [Diátaxis](https://diataxis.fr/) | 根据读者需要区分教程、操作指南、参考与解释 | 区分操作、方案与结果；不照搬四个目录，也不将其当成项目管理方法 |
| [Write the Docs：Docs as Code](https://www.writethedocs.org/guide/docs-as-code/) | 文档与代码共享版本控制、审查与自动检查流程 | 同一交付维护代码和受影响文档；私人文档继续忽略，不强制每项任务建 PR |
| [Software Engineering at Google：Documentation](https://abseil.io/resources/swe-book/html/ch10.html) | 明确维护责任、权威位置与更新机制，避免重复与陈旧文档 | 用户确认方向，Agent 随交付维护引用和事实；不用额外文档平台或团队审批角色 |
| [Kanban Guide，2025-05](https://kanbanguides.org/english/) | 定义工作流、控制在制工作、处理阻塞、持续改善 | 默认一个主要目标及简单优先顺序；未引入全部流动指标和 SLE，不自称完整 Kanban 实施 |
| [敏捷宣言原则](https://agilemanifesto.org/principles.html) | 持续交付可工作软件、欢迎反馈、保持简单与技术质量 | 小步验收和及时纠偏，不把敏捷理解为跳过设计或验收 |
| [arc42 概览](https://arc42.org/overview) | 架构文档区分目标、约束、结构、运行、部署和关键决策，允许裁剪 | 用于检查 ARCHITECTURE 的职责，不重写成十二节模板，不重复收录已有决策 |

## AI coding 与规格工具的交叉验证

| 来源 | 正文支持的经验 | 适用边界 |
| --- | --- | --- |
| [OpenSpec 工作流](https://github.com/Fission-AI/OpenSpec/blob/main/docs/workflows.md)与[规格编写](https://github.com/Fission-AI/OpenSpec/blob/main/docs/writing-specs.md) | 每次变更独立目录；允许探索、更新、实施、验证与归档之间反复迭代；一个变更保持一个意图，流程规模应匹配任务 | 默认多文件结构、CLI、规格合并不是 CareerAct 的必要依赖；工具自述不等于效率实证 |
| [GitHub Spec Kit](https://github.com/github/spec-kit/blob/main/README.md) | 需求、技术计划、任务、实现与验证有明确联系；当前还提供独立的缺陷修复和想法评估入口 | 不能把完整 SDD 顺序强制用于每次修改，也不把旧评测中的版本行为当成当前工具全部能力 |
| [Understanding Spec-Driven-Development](https://martinfowler.com/articles/exploring-gen-ai/sdd-3-tools.html)，Birgitta Böckeler，2025-10-15 | 区分跨会话通用背景与具体任务规格；指出冗长、重复文档造成审阅负担，固定流程难以匹配不同任务粒度，小步迭代有助于控制偏差 | 是作者对当时版本的实践分析，不是所有工具的最新评测；没有证明写规格本身必然提效 |
| [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices) | 提供可验证结果，及时纠偏，管理上下文，避免过度膨胀的规则文件；按任务选择规划强度 | 采用一般工程经验，不要求改用 Claude、照搬其命令或默认并行 Agent |

## CareerAct 的裁剪结论

1. 管理范围包括优先顺序、需求与设计、任务执行、质量验收、知识维护和交接，不限于变更记录。
2. PRD/ARCHITECTURE 保留顶层；handbook 管理全项目手册，topics 保存具体专题的知识与成果。
   生命周期与公开性作为属性管理，避免 product/engineering/archive/changes 混用分类维度。
3. 一个事实只有一个维护位置；STATUS 做进度与证据索引。专题从 README 起步，小修直接处理。
4. UI 决策用可见界面与操作验证；后端功能用完整路径验证；调优用可比较的实验验证。
   这是结合本项目返工问题的适配，不是上述工具共同强制的步骤。
5. 文件组织与代码隔离分开选择；不强制每项工作对应分支、PR、Sprint 或整套审批。
6. 完成的专题在原路径注明结果；稳定结论回到权威位置。可追溯的失效稿可清除，
   未提交/私人独有依据先保留；不把未完成研究丢进 archive 后继续当现行设计引用。
7. AGENTS 保留边界和入口，项目 SOP 只在开发手册维护；Skill 按需指导判断，研究按需读取。

不引入完整规格生成工具链、不建立通用项目管理系统、不复制私人职业资料作公开样本。
当前验证的是资料与方法的相容性，尚未通过连续真实交付证明效率收益。

## 如何判断是否值得继续用

在实际交付中观察：换会话能否快速恢复、能否找到决定的依据、偏差是否在大规模实施前被发现。
如果维护文件多于推进工作，优先合并文件、缩小必填内容；如果仍反复跑偏，补足对应的验证方式，
而不是继续增加通用规则。无需为这些观察新建指标系统或每轮复盘报告。

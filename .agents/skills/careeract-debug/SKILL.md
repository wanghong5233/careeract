---
name: careeract-debug
description: Diagnose unclear CareerAct integration failures across Web/BFF, FastAPI, PostgreSQL, LiteLLM, Temporal and Steel, especially when repeated fixes have failed. Use for evidence-driven cross-service debugging, not obvious one-line fixes or general questions.
---

# CareerAct 集成排障

先看 [开发指南](../../../docs/DEVELOPMENT.md) 的启动与验收边界；根据实际故障选择下面的步骤，
不为已明确的简单错误补齐一整套仪式。来源与适配见 [Skills 说明](../../../docs/SKILLS.md)。

## 缩小故障范围

1. 记录预期行为、实际结果、最小复现、当前配置模式以及最近相关改动。
2. 找到最后一个已确认成功的边界与第一个失败边界；缺日志时只增加定位该边界需要的观测。
3. 明确一个可证伪假设，进行最小实验；改变多个配置会失去归因，避免边试边堆补丁。
4. 假设成立后修根因，复跑原失败场景；若会重复发生，增加合适的回归检查。

| 链路 | 优先核对 |
| --- | --- |
| Web → BFF → API | Session 是否有效、JWT 是否获取/传递、issuer/audience/算法、JWKS 可达性、401 出自哪一层 |
| API → 数据库 | 服务是否启动、连接目标与 search_path、迁移版本、认证身份与 user_id 过滤 |
| Agent → LiteLLM → provider | 实际模型别名、provider 配置、密钥是否存在、限流/超时、响应与流在哪里结束 |
| Temporal → Worker → Activity | namespace/task queue、Worker 注册与连接、History、Activity 超时及重试语义 |
| Browser Service → Steel → 站点 | Steel 会话、租约所有者、页面实际状态、登录/验证码、确定性结果证据 |

基础设施未启动、代码缺失、配置错误和外部站点拒绝访问是不同问题；不要把它们都归为模型失败。
健康接口只证明该进程能响应，不证明它的外部依赖或业务调用成功。

## 控制实验的副作用

- 使用请求/任务/尝试 ID 关联证据，不打印整个环境、完整 Token、Cookie、DSN 或简历正文。
- 复现优先用测试数据和无副作用读取。真实发送或提交结果未知时先查证，不重跑整个任务。
- 不通过关闭鉴权、删除数据卷、清空 Profile 或吞掉异常来“修好”链路。
- 多轮无新证据时汇总已排除项并换诊断方法；涉及产品取舍时再讨论，不机械以失败次数断言架构错误。

## 交付

简要说明故障边界、支持根因的证据、改动与复测结果。环境阻塞时说明缺什么，保留可复现下一步。
只有当前阶段/能力/下一步改变时更新 STATUS，不为普通调试生成新的长期报告。

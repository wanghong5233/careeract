---
name: careeract-auth
description: Implement, diagnose or review CareerAct Better Auth sessions, same-origin Next.js BFF, short-lived JWT/JWKS verification and authentication schema changes. Use for auth integration or upgrades, not unrelated API CRUD or replacing the authentication stack.
---

# CareerAct 认证集成

先定位变更所在边界，不重新初始化已存在的认证。来源与适配见
[Skills 说明](../../../docs/SKILLS.md)，运行与检查见 [开发指南](../../../docs/DEVELOPMENT.md)。

## 阅读入口

- Web 配置：`apps/web/src/lib/auth.ts`、`auth-client.ts`、`server-env.ts`。
- 同源入口：`apps/web/src/app/api/auth/[...all]/route.ts`、`apps/web/src/app/api/agent/route.ts`。
- API 校验：`services/api/infrastructure/authentication.py`、`services/api/app/settings.py`。
- 身份上下文：`services/api/application/context.py`；迁移：`services/api/migrations/versions/`。

这些路径相对仓库根目录。先查 `apps/web/package-lock.json` 的实际 Better Auth 版本，
再使用匹配版本文档/类型定义；升级时区分当前版本行为与目标版本变化，不运行 `@latest` 来猜 API。

## 保持完整信任链

1. 浏览器持有 Better Auth 会话，通过同源 BFF 请求服务；BFF 根据真实 Session 获取短期 JWT。
2. API 校验签名/JWKS、允许算法、issuer、audience 和有效期；身份来自验证后的 `sub`。
3. 应用层传递认证 ActorContext，读取/写入必须限制到对应 user_id；资源 ID 不是访问许可。

检查 URL、代理来源、Cookie 的 Secure/SameSite 与当前 HTTP/HTTPS 环境是否一致。
本地 HTTP 与生产 HTTPS 要分清；不要关闭 CSRF、Origin 或 JWT 校验来消除报错。
Cookie、JWT 和招聘网站 Profile 属于不同信任边界，不能互相代用。
认证 SDK 单例不等于缓存用户会话；不能在模块级保存请求身份供其他请求复用。

## Schema 与版本变化

- CareerAct 使用 Alembic 维护认证 Schema。升级 Better Auth 或改变有 Schema 的插件时核对实际字段、索引和类型。
- 必要时用匹配版本的 Schema 输出作比对输入，再编写新 Alembic revision；不直接执行 Better Auth CLI migration。
- 不覆盖 `0001_auth_schema.py` 或其他已存在 revision，不以 PostgreSQL 首次初始化脚本更新已有数据库。
- 明确数据迁移、非空默认值与唯一性影响，在可丢弃的测试数据库验证旧版到新版路径；不拿用户库试错。
- Session、缓存撤销与 JWT 过期有不同时间语义；报告实际行为，不宣称退出登录天然立刻撤销所有已签发 JWT。

## 验收与交付

按改动验证真实登录链路以及相关负例：未登录、过期/错误签名、错误 issuer/audience、跨用户访问。
涉及迁移时覆盖已有数据库升级；涉及流式 BFF 时确认身份与请求取消能传到正确边界。
不能用 `/health` 或 mock JWT 的单测替代完整集成；报告哪些层真实运行、哪些替代或尚未验证。
日志只留关联 ID、错误类型和脱敏配置差异，不输出 secret、完整 JWT、Cookie 或数据库连接密码。

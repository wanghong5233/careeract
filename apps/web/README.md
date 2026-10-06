# CareerAct Web

This directory contains the Next.js Agent shell. Start the complete local
development environment from the repository root:

```powershell
npm --prefix apps/web run dev
```

The launcher selects a consistent Web/API debug-port pair and prints the URLs.
It falls back through the development pool when a candidate is occupied, reuses
an existing instance, and retries failed services with a bounded recovery budget.
Use `dev:status` to see the current URL and `dev:stop` to cleanly stop both services.
See the [repository README](../../README.md) and [development guide](../../docs/handbook/DEVELOPMENT.md#配置与启动)
for setup, migrations, checks, and service boundaries.

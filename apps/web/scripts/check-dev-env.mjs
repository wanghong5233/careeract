import { createRequire } from "node:module";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const { loadEnvConfig } = require("@next/env");

export const devWebOrigin = "http://localhost:3100";
export const devApiOrigin = "http://localhost:8000";

export function validateDevConfig(apiEnv, webEnv) {
  const expectedApi = {
    AUTH_ISSUER: devWebOrigin,
    AUTH_AUDIENCE: devWebOrigin,
    AUTH_JWKS_URL: `${devWebOrigin}/api/auth/jwks`,
  };
  const expectedWeb = {
    BETTER_AUTH_URL: devWebOrigin,
    API_BASE_URL: devApiOrigin,
  };
  const mismatches = [];
  for (const [source, env, expected] of [
    ["API", apiEnv, expectedApi],
    ["Web", webEnv, expectedWeb],
  ]) {
    for (const [name, value] of Object.entries(expected)) {
      if (env[name] !== value) mismatches.push(`${source} ${name}`);
    }
  }
  if (mismatches.length) {
    throw new Error(
      `开发配置不一致：${mismatches.join("、")}。按开发指南统一 Web 3100 / API 8000；不自动换端口。`,
    );
  }
}

export function checkDevConfig() {
  const webDirectory = resolve(dirname(fileURLToPath(import.meta.url)), "..");
  const rootDirectory = resolve(webDirectory, "../..");
  const quietLog = { info() {}, error() {} };
  const apiConfig = spawnSync("uv", [
    "run", "--package", "careeract-api", "python", "-c",
    'import json; from services.api.app.settings import Settings; s = Settings(); print(json.dumps({"AUTH_ISSUER": s.auth_issuer, "AUTH_AUDIENCE": s.auth_audience, "AUTH_JWKS_URL": str(s.auth_jwks_url)}))',
  ], { cwd: rootDirectory, encoding: "utf8", windowsHide: true });
  if (apiConfig.status !== 0) {
    throw new Error("无法加载 API 配置。请按开发指南核对项目依赖与必填配置；未启动服务。");
  }
  const apiEnv = JSON.parse(apiConfig.stdout);
  const webEnv = loadEnvConfig(webDirectory, true, quietLog, true).combinedEnv;
  validateDevConfig(apiEnv, webEnv);
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    checkDevConfig();
    console.log(`开发配置一致：Web ${devWebOrigin} / API ${devApiOrigin}`);
  } catch (error) {
    console.error(error instanceof Error ? error.message : "开发配置校验失败");
    process.exitCode = 1;
  }
}

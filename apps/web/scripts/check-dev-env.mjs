import { createRequire } from "node:module";
import net from "node:net";
import { spawnSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);
const { loadEnvConfig } = require("@next/env");

export const devWebPort = 43110;
export const devApiPort = 43111;
export const devWebOrigin = `http://localhost:${devWebPort}`;
export const devApiOrigin = `http://localhost:${devApiPort}`;
export const devPortPairs = Array.from({ length: 8 }, (_, index) => ({
  web: devWebPort + index * 10,
  api: devApiPort + index * 10,
}));

export function outsideWindowsDynamicRange(pairs, output) {
  const values = [...output.matchAll(/:\s*(\d+)/g)].map(match => Number(match[1]));
  if (values.length !== 2) throw new Error("无法解析 Windows TCP 动态端口范围，请运行 netsh interface ipv4 show dynamicport tcp 核对。");
  const [start, count] = values;
  return pairs.filter(pair => [pair.web, pair.api].every(port => port < start || port >= start + count));
}

export function availableWindowsPortPool() {
  if (process.platform !== "win32") return devPortPairs;
  let pairs = devPortPairs;
  for (const family of ["ipv4", "ipv6"]) {
    const result = spawnSync("netsh.exe", ["interface", family, "show", "dynamicport", "tcp"], { encoding: "utf8", windowsHide: true });
    if (result.status !== 0) throw new Error(`无法核对 Windows ${family} 动态端口范围。`);
    pairs = outsideWindowsDynamicRange(pairs, result.stdout);
  }
  if (!pairs.length) throw new Error("全部调试端口落入 Windows TCP 动态分配范围；请先修正端口池，不修改系统设置。");
  return pairs;
}

function portOwner(port) {
  if (process.platform !== "win32") return "用 lsof/ss 查看占用进程";
  const result = spawnSync("powershell.exe", [
    "-NoProfile", "-Command",
    `$connection = Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue | Select-Object -First 1; if ($connection) { $process = Get-Process -Id $connection.OwningProcess -ErrorAction SilentlyContinue; if ($process) { \"PID=$($connection.OwningProcess) $($process.ProcessName)\" } else { \"PID=$($connection.OwningProcess)\" } }`,
  ], { encoding: "utf8", windowsHide: true });
  return result.status === 0 && result.stdout.trim() ? result.stdout.trim() : "无法读取占用进程";
}

export function checkPort(port) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once("error", error => {
      reject(error);
    });
    server.listen({ host: "127.0.0.1", port, exclusive: true }, () => server.close(() => resolve()));
  });
}

export async function findAvailableDevPorts(pairs = devPortPairs, report = console.warn) {
  const unavailable = [];
  for (const ports of pairs) {
    try {
      await checkPort(ports.web);
      await checkPort(ports.api);
      return ports;
    } catch (error) {
      if (!["EADDRINUSE", "EACCES", "EPERM"].includes(error.code)) throw error;
      const detail = `${error.code}，Web ${portOwner(ports.web)}；API ${portOwner(ports.api)}`;
      unavailable.push(detail);
      report(`调试端口对 ${ports.web}/${ports.api} 不可用（${detail}），尝试下一对。`);
    }
  }
  throw new Error(`调试端口池已耗尽：${unavailable.join("；")}`);
}

export function devEnvironment(ports, inherited = process.env) {
  const webOrigin = `http://localhost:${ports.web}`;
  return {
    ...inherited,
    BETTER_AUTH_URL: webOrigin,
    API_BASE_URL: `http://localhost:${ports.api}`,
    AUTH_ISSUER: webOrigin,
    AUTH_AUDIENCE: webOrigin,
    AUTH_JWKS_URL: `${webOrigin}/api/auth/jwks`,
  };
}

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
      `开发配置不一致：${mismatches.join("、")}。按开发指南统一 Web ${devWebPort} / API ${devApiPort}；不自动换端口。`,
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

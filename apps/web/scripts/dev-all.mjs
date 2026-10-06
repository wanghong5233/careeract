import { spawn, spawnSync } from "node:child_process";
import { appendFileSync, existsSync, mkdirSync, readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { availableWindowsPortPool, checkDevConfig, devEnvironment, findAvailableDevPorts } from "./check-dev-env.mjs";

const webDirectory = resolve(import.meta.dirname, "..");
const rootDirectory = resolve(webDirectory, "../..");
const stateDirectory = resolve(rootDirectory, "data/dev");
const lockPath = resolve(stateDirectory, "careeract.lock");
const statePath = resolve(stateDirectory, "careeract.json");
const stopPath = resolve(stateDirectory, "careeract.stop");
const logPath = resolve(stateDirectory, "careeract.log");

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

export function processAlive(pid) {
  if (!Number.isInteger(pid) || pid <= 0) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    if (error.code === "ESRCH") return false;
    throw error;
  }
}

export function recoveryDelay(attempt) {
  return attempt > 3 ? null : 1000 * 2 ** (attempt - 1);
}

export async function stopProcessTree(child) {
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
  if (process.platform === "win32") {
    const result = spawnSync("taskkill.exe", ["/PID", String(child.pid), "/T", "/F"], { windowsHide: true, encoding: "utf8" });
    if (result.status !== 0 && processAlive(child.pid)) throw new Error(`无法停止开发子进程树 PID=${child.pid}`);
  } else {
    try {
      process.kill(-child.pid, "SIGTERM");
    } catch (error) {
      if (error.code !== "ESRCH") throw error;
    }
    await delay(500);
    if (processAlive(child.pid)) process.kill(-child.pid, "SIGKILL");
  }
}

export async function healthy(url) {
  try {
    const response = await fetch(url, { redirect: "manual", signal: AbortSignal.timeout(3000) });
    await response.body?.cancel();
    return response.status === 200;
  } catch (error) {
    if (error instanceof TypeError || error.name === "TimeoutError" || error.name === "AbortError") return false;
    throw error;
  }
}

function log(message) {
  const line = `${new Date().toISOString()} ${message}`;
  appendFileSync(logPath, `${line}\n`);
  console.log(line);
}

async function existingInstance() {
  for (let attempt = 0; attempt < 20; attempt++) {
    const owner = readJson(lockPath);
    if (!owner || !processAlive(owner.pid)) return null;
    const state = readJson(statePath);
    if (state?.pid === owner.pid) return state;
    await delay(250);
  }
  throw new Error("现有开发启动器仍在初始化；稍后用 npm run dev:status 查看，不创建第二套服务。");
}

function showState(state) {
  console.log(state ? `CareerAct ${state.status}：Web ${state.webUrl ?? "准备中"} / API ${state.apiUrl ?? "准备中"}，PID=${state.pid}\n日志：${logPath}` : "CareerAct 开发服务未运行。");
}

async function main() {
  mkdirSync(stateDirectory, { recursive: true });
  const existing = await existingInstance();
  if (process.argv.includes("--generate-api")) {
    if (existing?.status !== "ready") throw new Error("先启动开发服务并等待 ready，再生成 API 类型。");
    const child = spawn(process.execPath, [resolve(webDirectory, "node_modules/openapi-typescript/bin/cli.js"), `${existing.apiUrl}/openapi.json`, "-o", "src/lib/api-schema.d.ts"], { cwd: webDirectory, stdio: "inherit" });
    const code = await new Promise((resolve, reject) => { child.once("error", reject); child.once("exit", resolve); });
    if (code !== 0) throw new Error("API 类型生成失败。");
    return;
  }
  if (process.argv.includes("--status")) {
    showState(existing);
    return;
  }
  if (process.argv.includes("--stop")) {
    if (!existing) return showState(null);
    writeFileSync(stopPath, String(existing.pid));
    for (let attempt = 0; attempt < 60; attempt++) {
      if (!processAlive(existing.pid)) return console.log("CareerAct 开发服务和子进程已停止。");
      await delay(250);
    }
    throw new Error(`停止尚未完成，检查 ${logPath}`);
  }
  if (existing) {
    showState(existing);
    if (existing.status === "failed") throw new Error("现有启动器已停止恢复；先 dev:stop，修正日志中的原因后再 dev。");
    return;
  }
  const stale = readJson(lockPath);
  if (stale) {
    if (processAlive(stale.pid)) {
      showState(await existingInstance());
      return;
    }
    if (readJson(lockPath)?.pid === stale.pid) unlinkSync(lockPath);
  }
  try {
    writeFileSync(lockPath, JSON.stringify({ pid: process.pid }), { flag: "wx" });
  } catch (error) {
    if (error.code !== "EEXIST") throw error;
    showState(await existingInstance());
    return;
  }

  let stopping = false;
  let children = [];
  let state = { pid: process.pid, status: "starting", webUrl: null, apiUrl: null, services: {} };
  function saveState() {
    writeFileSync(`${statePath}.tmp`, JSON.stringify(state, null, 2));
    renameSync(`${statePath}.tmp`, statePath);
  }
  process.on("SIGINT", () => { stopping = true; });
  process.on("SIGTERM", () => { stopping = true; });
  const control = setInterval(() => {
    if (existsSync(stopPath) && readFileSync(stopPath, "utf8").trim() === String(process.pid)) stopping = true;
  }, 250);
  function startService(name, command, args, cwd, environment) {
    const child = spawn(command, args, { cwd, env: environment, windowsHide: true, detached: process.platform !== "win32", stdio: ["ignore", "pipe", "pipe"] });
    const service = { name, child, command, args, cwd, environment, restarts: 0, failures: 0, exited: false, bindFailed: false };
    for (const stream of [child.stdout, child.stderr]) stream.on("data", data => {
      const message = data.toString();
      appendFileSync(logPath, message);
      process.stdout.write(message);
      if (/EADDRINUSE|EACCES|WinError 10013|address already in use/i.test(message)) service.bindFailed = true;
    });
    child.once("error", error => { service.exited = true; log(`${name} 启动失败：${error.code}`); });
    child.once("exit", (code, signal) => { service.exited = true; log(`${name} 退出：${code ?? signal}`); });
    state.services[name] = child.pid ?? null;
    saveState();
    return service;
  }
  async function stopServices() {
    await Promise.all(children.map(service => stopProcessTree(service.child)));
    children = [];
  }
  async function waitReady() {
    const deadline = Date.now() + 90000;
    while (!stopping && Date.now() < deadline) {
      if (children.some(service => service.exited)) return false;
      const results = await Promise.all([healthy(`${state.webUrl}/sign-in`), healthy(`${state.apiUrl}/health`)]);
      if (results.every(Boolean)) return true;
      await delay(500);
    }
    return false;
  }
  try {
    saveState();
    checkDevConfig();
    const portPool = availableWindowsPortPool();
    let remainingPairs = portPool;
    while (!stopping) {
      const ports = await findAvailableDevPorts(remainingPairs, log);
      const environment = devEnvironment(ports);
      state = { ...state, status: "starting", webUrl: environment.BETTER_AUTH_URL, apiUrl: environment.API_BASE_URL, services: {} };
      saveState();
      log(`启动 Web ${state.webUrl} / API ${state.apiUrl}`);
      children = [
        startService("web", process.execPath, [resolve(webDirectory, "node_modules/next/dist/bin/next"), "dev", "--hostname", "127.0.0.1", "--port", String(ports.web)], webDirectory, environment),
        startService("api", "uv", ["run", "--package", "careeract-api", "python", "-m", "uvicorn", "services.api.app.main:app", "--host", "127.0.0.1", "--port", String(ports.api), "--reload", "--reload-dir", "services"], rootDirectory, environment),
      ];
      if (await waitReady()) break;
      const bindFailed = children.some(service => service.bindFailed);
      await stopServices();
      if (stopping) return;
      if (!bindFailed) throw new Error("开发服务启动未就绪；查看日志中的编译、依赖或配置错误。");
      remainingPairs = portPool.filter(pair => pair.web > ports.web);
      if (!remainingPairs.length) throw new Error("调试端口池在实际启动时耗尽。");
      log("探测后端口被占用，清理本次子进程后重新选择端口对。");
    }
    if (stopping) return;
    state.status = "ready";
    saveState();
    log(`已就绪：${state.webUrl}；状态：npm --prefix apps/web run dev:status`);
    while (!stopping) {
      await delay(5000);
      for (let index = 0; index < children.length && !stopping; index++) {
        const service = children[index];
        const url = service.name === "web" ? `${state.webUrl}/sign-in` : `${state.apiUrl}/health`;
        service.failures = await healthy(url) ? 0 : service.failures + 1;
        if (!service.exited && service.failures < 3) continue;
        const backoff = recoveryDelay(service.restarts + 1);
        if (backoff === null) throw new Error(`${service.name} 已连续恢复 3 次，停止自动恢复以保留错误证据。`);
        state.status = "recovering";
        saveState();
        log(`${service.name} 不可用，${backoff / 1000} 秒后在原端口恢复。不会重放 Agent 请求。`);
        await stopProcessTree(service.child);
        await delay(backoff);
        if (stopping) break;
        const replacement = startService(service.name, service.command, service.args, service.cwd, service.environment);
        replacement.restarts = service.restarts + 1;
        children[index] = replacement;
        if (!await waitReady()) replacement.failures = 3;
        else { state.status = "ready"; saveState(); log(`${service.name} 恢复成功。`); }
      }
    }
  } catch (error) {
    state.status = "failed";
    saveState();
    log(`开发服务失败：${error.message}`);
    process.exitCode = 1;
  } finally {
    clearInterval(control);
    await stopServices();
    state.status = process.exitCode ? "failed" : "stopped";
    state.services = {};
    saveState();
    if (readJson(lockPath)?.pid === process.pid) unlinkSync(lockPath);
    if (existsSync(stopPath) && readFileSync(stopPath, "utf8").trim() === String(process.pid)) unlinkSync(stopPath);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}

export const launcherPath = fileURLToPath(import.meta.url);

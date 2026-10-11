import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { readFileSync } from "node:fs";
import net from "node:net";
import test from "node:test";
import { devApiOrigin, devApiPort, devEnvironment, devPortPairs, devWebOrigin, devWebPort, findAvailableDevPorts, outsideWindowsDynamicRange, validateDevConfig } from "../scripts/check-dev-env.mjs";
import { healthy, launcherProcessAlive, processAlive, recoverService, recoveryDelay, recordServiceHealth, stopProcessTree } from "../scripts/dev-all.mjs";

const apiEnv = {
  AUTH_ISSUER: devWebOrigin,
  AUTH_AUDIENCE: devWebOrigin,
  AUTH_JWKS_URL: `${devWebOrigin}/api/auth/jwks`,
};
const webEnv = { BETTER_AUTH_URL: devWebOrigin, API_BASE_URL: devApiOrigin };

test("launcher lock distinguishes an unrelated living process on Windows", () => {
  assert.equal(processAlive(process.pid), true);
  assert.equal(launcherProcessAlive(-1), false);
  if (process.platform === "win32") assert.equal(launcherProcessAlive(process.pid), false);
});

test("development origins agree and auth drift fails before startup", () => {
  assert.doesNotThrow(() => validateDevConfig(apiEnv, webEnv));
  for (const name of Object.keys(apiEnv)) {
    assert.throws(() => validateDevConfig({ ...apiEnv, [name]: "http://localhost:3000" }, webEnv), new RegExp(name));
  }
  for (const name of Object.keys(webEnv)) {
    assert.throws(() => validateDevConfig(apiEnv, { ...webEnv, [name]: "http://localhost:3000" }), new RegExp(name));
  }
  assert.throws(() => validateDevConfig({}, {}), /开发配置不一致/);
});

test("Windows dynamic allocation is checked rather than assuming the default range", () => {
  assert.deepEqual(outsideWindowsDynamicRange(devPortPairs, "Start Port : 1024\nNumber of Ports : 13977"), devPortPairs);
  assert.deepEqual(outsideWindowsDynamicRange(devPortPairs, "Start Port : 43000\nNumber of Ports : 1000"), []);
  assert.throws(() => outsideWindowsDynamicRange(devPortPairs, "unreadable"), /无法解析/);
});

test("launchers use explicit ports and checked-in examples match", () => {
  const scripts = JSON.parse(readFileSync(new URL("../package.json", import.meta.url))).scripts;
  assert.ok(devWebPort > 40000 && devWebPort < 49152);
  assert.ok(devApiPort > 40000 && devApiPort < 49152);
  assert.notEqual(devWebPort, devApiPort);
  assert.equal(devPortPairs.length, 8);
  assert.deepEqual(devPortPairs[0], { web: devWebPort, api: devApiPort });
  assert.match(scripts.dev, /dev-all/);
  assert.match(scripts["dev:status"], /dev-all.*--status/);
  assert.match(scripts["dev:stop"], /dev-all.*--stop/);
  assert.match(scripts["generate:api"], /dev-all.*--generate-api/);
  const readEnv = (path) => Object.fromEntries(
    readFileSync(new URL(path, import.meta.url), "utf8").split(/\r?\n/)
      .filter((line) => line.includes("=")).map((line) => {
        const separator = line.indexOf("=");
        return [line.slice(0, separator), line.slice(separator + 1)];
      }),
  );
  assert.doesNotThrow(() => validateDevConfig(readEnv("../../../.env.example"), readEnv("../.env.example")));
});

test("an occupied API port skips the entire pair and exhaustion is explicit", async () => {
  const blocker = net.createServer();
  await new Promise(resolve => blocker.listen(0, "127.0.0.1", resolve));
  const occupied = blocker.address().port;
  const freePorts = [];
  for (let index = 0; index < 3; index++) {
    const probe = net.createServer();
    await new Promise(resolve => probe.listen(0, "127.0.0.1", resolve));
    freePorts.push(probe.address().port);
    await new Promise(resolve => probe.close(resolve));
  }
  const blockedPair = { web: freePorts[0], api: occupied };
  const availablePair = { web: freePorts[1], api: freePorts[2] };
  try {
    assert.deepEqual(await findAvailableDevPorts([blockedPair, availablePair], () => {}), availablePair);
    await assert.rejects(findAvailableDevPorts([blockedPair], () => {}), /端口池已耗尽/);
  } finally {
    await new Promise(resolve => blocker.close(resolve));
  }
});

test("fallback ports replace every auth and BFF origin without replacing credentials", () => {
  const environment = devEnvironment({ web: 43120, api: 43121 }, { BETTER_AUTH_SECRET: "synthetic-test-value", AUTH_ISSUER: "stale" });
  assert.equal(environment.BETTER_AUTH_URL, "http://localhost:43120");
  assert.equal(environment.AUTH_ISSUER, environment.BETTER_AUTH_URL);
  assert.equal(environment.AUTH_AUDIENCE, environment.BETTER_AUTH_URL);
  assert.equal(environment.AUTH_JWKS_URL, `${environment.BETTER_AUTH_URL}/api/auth/jwks`);
  assert.equal(environment.API_BASE_URL, "http://localhost:43121");
  assert.equal(environment.BETTER_AUTH_SECRET, "synthetic-test-value");
});

test("recovery has bounded exponential backoff and unreachable health is a failure", async () => {
  assert.deepEqual([1, 2, 3, 4].map(recoveryDelay), [1000, 2000, 4000, null]);
  const probe = net.createServer();
  await new Promise(resolve => probe.listen(0, "127.0.0.1", resolve));
  const port = probe.address().port;
  await new Promise(resolve => probe.close(resolve));
  assert.equal(await healthy(`http://127.0.0.1:${port}/health`), false);
});

test("stable health resets consecutive recovery budget but brief recovery does not", () => {
  const service = { failures: 3, restarts: 3, healthySince: null };
  recordServiceHealth(service, true, 1000);
  recordServiceHealth(service, true, 60_999);
  assert.equal(service.restarts, 3);
  recordServiceHealth(service, false, 61_000);
  assert.equal(service.failures, 1);
  assert.equal(service.healthySince, null);
  recordServiceHealth(service, true, 62_000);
  recordServiceHealth(service, true, 122_000);
  assert.equal(service.restarts, 0);
  assert.equal(service.failures, 0);
  const launcher = readFileSync(new URL("../scripts/dev-all.mjs", import.meta.url), "utf8");
  assert.match(launcher, /"--reload-dir", "services\/api"/);
});

test("exhausted API recovery stops only its own process and preserves the Web service", async () => {
  const web = { name: "web", child: { pid: 101 }, restarts: 0 };
  const api = { name: "api", child: { pid: 102 }, restarts: 3 };
  const stopped = [];
  let started = 0;
  const options = {
    stop: async child => { stopped.push(child.pid); },
    start: () => { started++; },
    wait: async () => { assert.fail("exhausted recovery must not wait or retry"); },
    report: () => {},
  };
  assert.equal(await recoverService(api, options), api);
  assert.equal(api.recoveryStopped, true);
  assert.equal(await recoverService(api, options), api);
  assert.deepEqual(stopped, [102]);
  assert.equal(started, 0);
  assert.equal(web.recoveryStopped, undefined);
  assert.equal(web.child.pid, 101);
});

test("service recovery preserves launch settings and cancellation prevents restart", async () => {
  for (const cancelled of [false, true]) {
    const service = {
      name: "api", child: { pid: 102 }, restarts: 1,
      command: "uv", args: ["--port", "43111"], cwd: "synthetic", environment: { SYNTHETIC: "yes" },
    };
    const events = [];
    const replacement = { restarts: 0 };
    const result = await recoverService(service, {
      stop: async child => events.push(["stop", child.pid]),
      wait: async duration => events.push(["wait", duration]),
      start: (...args) => { events.push(["start", ...args]); return replacement; },
      isStopping: () => cancelled,
      report: () => {},
    });
    assert.deepEqual(events.slice(0, 2), [["stop", 102], ["wait", 2000]]);
    if (cancelled) {
      assert.equal(events.length, 2);
      assert.equal(result, service);
    } else {
      assert.deepEqual(events[2], ["start", service.name, service.command, service.args, service.cwd, service.environment]);
      assert.equal(result, replacement);
      assert.equal(result.restarts, 2);
    }
  }
});

test("real process recovery exhaustion leaves the healthy sibling HTTP server reachable", async () => {
  const children = [];
  const startServer = async name => {
    const child = spawn(process.execPath, ["--input-type=module", "-e",
      'import http from "node:http"; const server = http.createServer((request, response) => response.end("synthetic")); server.listen(0, "127.0.0.1", () => console.log(server.address().port));',
    ], { windowsHide: true, detached: process.platform !== "win32", stdio: ["ignore", "pipe", "pipe"] });
    children.push(child);
    const port = await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error("synthetic HTTP server startup timed out")), 5000);
      child.once("error", error => { clearTimeout(timeout); reject(error); });
      child.stdout.once("data", data => { clearTimeout(timeout); resolve(Number(data.toString().trim())); });
    });
    return { name, child, url: `http://127.0.0.1:${port}/health`, restarts: 3 };
  };
  try {
    const web = await startServer("web");
    const api = await startServer("api");
    assert.equal(await healthy(web.url), true);
    assert.equal(await healthy(api.url), true);
    await recoverService(api, {
      stop: stopProcessTree,
      start: () => assert.fail("exhausted recovery must not spawn another process"),
      report: () => {},
    });
    assert.equal(await healthy(api.url), false);
    assert.equal(await healthy(web.url), true);
    assert.equal(processAlive(web.child.pid), true);
  } finally {
    await Promise.all(children.map(stopProcessTree));
  }
});

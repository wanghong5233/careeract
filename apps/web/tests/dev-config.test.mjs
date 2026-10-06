import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import net from "node:net";
import test from "node:test";
import { devApiOrigin, devApiPort, devEnvironment, devPortPairs, devWebOrigin, devWebPort, findAvailableDevPorts, outsideWindowsDynamicRange, validateDevConfig } from "../scripts/check-dev-env.mjs";
import { healthy, recoveryDelay } from "../scripts/dev-all.mjs";

const apiEnv = {
  AUTH_ISSUER: devWebOrigin,
  AUTH_AUDIENCE: devWebOrigin,
  AUTH_JWKS_URL: `${devWebOrigin}/api/auth/jwks`,
};
const webEnv = { BETTER_AUTH_URL: devWebOrigin, API_BASE_URL: devApiOrigin };

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

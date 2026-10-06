import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { devApiOrigin, devWebOrigin, validateDevConfig } from "../scripts/check-dev-env.mjs";

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

test("launchers use explicit ports and checked-in examples match", () => {
  const scripts = JSON.parse(readFileSync(new URL("../package.json", import.meta.url))).scripts;
  assert.match(scripts.dev, /--port 3100/);
  assert.match(scripts.predev, /check-dev-env/);
  assert.match(scripts["dev:api"], /check-dev-env.*&&.*--directory \.\.\/\.\..*python -m uvicorn.*--port 8000.*--reload-dir services/);
  const readEnv = (path) => Object.fromEntries(
    readFileSync(new URL(path, import.meta.url), "utf8").split(/\r?\n/)
      .filter((line) => line.includes("=")).map((line) => {
        const separator = line.indexOf("=");
        return [line.slice(0, separator), line.slice(separator + 1)];
      }),
  );
  assert.doesNotThrow(() => validateDevConfig(readEnv("../../../.env.example"), readEnv("../.env.example")));
});

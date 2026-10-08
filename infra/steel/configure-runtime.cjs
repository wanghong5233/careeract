const fs = require("node:fs");

const sourcePath = "/app/api/build/services/cdp/instrumentation/target-manager.js";
const source = fs.readFileSync(sourcePath, "utf8");
const original = 'await enable("Runtime");';
if (source.split(original).length - 1 !== 3) {
  throw new Error("Pinned Steel Runtime observation sites changed");
}
fs.writeFileSync(sourcePath, source.replaceAll(original,
  'if (process.env.CAREERACT_STEEL_RUNTIME_OBSERVATION !== "false") { await enable("Runtime"); }'));

const controllerPath = "/app/api/build/modules/sessions/sessions.controller.js";
const controller = fs.readFileSync(controllerPath, "utf8");
const storageExport = "const browserVersion = await server.cdpService.getBrowserState();";
const storageField = "            browserVersion,";
if (controller.split(storageExport).length - 1 !== 1 ||
    controller.split(storageField).length - 1 !== 1) {
  throw new Error("Pinned Steel live-details storage export changed");
}
fs.writeFileSync(controllerPath, controller.replace(storageExport,
  "const browserVersion = await pages[0].browser().version();"));

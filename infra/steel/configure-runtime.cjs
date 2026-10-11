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

const castingPath = "/app/api/build/plugins/browser-socket/casting.handler.js";
const casting = fs.readFileSync(castingPath, "utf8");
const queryMarker = 'const queryParams = new URLSearchParams(request.url?.split("?")[1] || "");';
const frontMarker = "                await targetPage.bringToFront();";
const inputMarker = '                        const data = JSON.parse(message.toString());';
const metricsMarker = "                await targetClient.send(\"Page.setDeviceMetricsOverride\", {";
const screencastMarker = "                await targetClient.send(\"Page.startScreencast\", {";
const connectMarker = "            browser = await puppeteer.connect({\n                browserWSEndpoint: `ws://${env.HOST}:${env.PORT}`,\n            });";
if (casting.split(queryMarker).length - 1 !== 1 ||
    casting.split(frontMarker).length - 1 !== 1 ||
    casting.split(inputMarker).length - 1 !== 1 ||
    casting.split(metricsMarker).length - 1 !== 1 ||
    casting.split(screencastMarker).length - 1 !== 1 ||
    casting.split(connectMarker).length - 1 !== 1) {
  throw new Error("Pinned Steel casting handler layout changed");
}
let readonlyCasting = casting.replace(
  queryMarker,
  `${queryMarker}\n    const readonlyMode = queryParams.get("readOnly") === "true";`,
);
readonlyCasting = readonlyCasting.replace(
  connectMarker,
  "            browser = await puppeteer.connect({\n" +
  "                browserWSEndpoint: `ws://${env.HOST}:${env.PORT}`,\n" +
  "                defaultViewport: null,\n" +
  "            });",
);
readonlyCasting = readonlyCasting.replace(
  frontMarker,
  "                if (!readonlyMode) await targetPage.bringToFront();",
);
readonlyCasting = readonlyCasting.replace(
  inputMarker,
  `${inputMarker}\n                        if (readonlyMode) return;`,
);
readonlyCasting = readonlyCasting.replace(
  metricsMarker,
  "                let readonlyViewport = null;\n" +
  "                if (readonlyMode) {\n" +
  "                    const metrics = await targetPage.evaluate(() => ({\n" +
  "                        width: window.innerWidth,\n" +
  "                        height: window.innerHeight,\n" +
  "                        deviceScaleFactor: window.devicePixelRatio,\n" +
  "                    }));\n" +
  "                    readonlyViewport = {\n" +
  "                        width: metrics.width,\n" +
  "                        height: metrics.height,\n" +
  "                        deviceScaleFactor: metrics.deviceScaleFactor,\n" +
  "                    };\n" +
  "                }\n" +
  "                if (!readonlyMode) {\n" + metricsMarker,
);
const metricsEnd = "                    deviceScaleFactor: isMobile ? 3 : 1,\n                });";
if (readonlyCasting.split(metricsEnd).length - 1 !== 1) {
  throw new Error("Pinned Steel casting metrics layout changed");
}
readonlyCasting = readonlyCasting.replace(
  metricsEnd,
  `${metricsEnd}\n                }`,
);
const screencastEnd = "                    maxHeight: height,\n                });";
if (readonlyCasting.split(screencastEnd).length - 1 !== 1) {
  throw new Error("Pinned Steel screencast layout changed");
}
readonlyCasting = readonlyCasting.replace(
  screencastEnd,
  `${screencastEnd}\n` +
  "                if (readonlyViewport?.width && readonlyViewport?.height) {\n" +
  "                    await targetClient.send(\"Page.setDeviceMetricsOverride\", {\n" +
  "                        screenWidth: readonlyViewport.width,\n" +
  "                        screenHeight: readonlyViewport.height,\n" +
  "                        width: readonlyViewport.width,\n" +
  "                        height: readonlyViewport.height,\n" +
  "                        deviceScaleFactor: readonlyViewport.deviceScaleFactor || 1,\n" +
  "                        mobile: false,\n" +
  "                    });\n" +
  "                }",
);
fs.writeFileSync(castingPath, readonlyCasting);

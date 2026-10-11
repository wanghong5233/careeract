const assert = require("node:assert/strict");
const test = require("node:test");
const { viewerCoordinates } = require("./viewer-coordinates.cjs");

const canvas = (left, top, width, height) => ({ getBoundingClientRect: () => ({ left, top, width, height }) });
const metadata = { deviceWidth: 1920, deviceHeight: 1080, pageScaleFactor: 1, offsetTop: 0 };

test("rendered frame maps to viewport coordinates independently of frame pixels or host DPR", () => {
  for (const [left, top, width, height] of [[36, 40, 1200, 675], [100, 80, 640, 360], [0, 0, 1920, 1080]]) {
    assert.deepEqual(viewerCoordinates({ clientX: left + width / 2, clientY: top + height / 2 }, canvas(left, top, width, height), metadata), { x: 960, y: 540 });
  }
});

test("browser zoom and top offset map to CSS viewport, without adding document scroll", () => {
  assert.deepEqual(viewerCoordinates({ clientX: 600, clientY: 400 }, canvas(0, 40, 1200, 720), { ...metadata, pageScaleFactor: 2, offsetTop: 20 }), { x: 480, y: 260 });
});

test("missing metadata, collapsed frame and points outside the drawn canvas cannot dispatch input", () => {
  const surface = canvas(100, 80, 640, 360);
  assert.equal(viewerCoordinates({ clientX: 99, clientY: 100 }, surface, metadata), null);
  assert.equal(viewerCoordinates({ clientX: 740, clientY: 100 }, surface, metadata), null);
  assert.equal(viewerCoordinates({ clientX: 200, clientY: 79 }, surface, metadata), null);
  assert.equal(viewerCoordinates({ clientX: 200, clientY: 440 }, surface, metadata), null);
  assert.equal(viewerCoordinates({ clientX: 200, clientY: 100 }, surface, undefined), null);
  assert.equal(viewerCoordinates({ clientX: 200, clientY: 100 }, canvas(100, 80, 0, 0), metadata), null);
  assert.equal(viewerCoordinates({ clientX: 200, clientY: 100 }, surface, { ...metadata, pageScaleFactor: 0 }), null);
});

function viewerCoordinates(event, canvas, frameMetadata) {
  const rect = canvas.getBoundingClientRect();
  const width = frameMetadata?.deviceWidth;
  const height = frameMetadata?.deviceHeight;
  const zoom = frameMetadata?.pageScaleFactor;
  const offset = frameMetadata?.offsetTop;
  if (![width, height, zoom, offset, rect.width, rect.height, event.clientX, event.clientY].every(Number.isFinite)
      || width <= 0 || height <= 0 || zoom <= 0 || offset < 0 || rect.width <= 0 || rect.height <= 0) return null;
  const horizontal = (event.clientX - rect.left) / rect.width;
  const vertical = (event.clientY - rect.top) / rect.height;
  if (horizontal < 0 || horizontal >= 1 || vertical < 0 || vertical >= 1) return null;
  const x = horizontal * width / zoom;
  const y = (vertical * height - offset) / zoom;
  if (y < 0) return null;
  return { x, y };
}

module.exports = { viewerCoordinates };

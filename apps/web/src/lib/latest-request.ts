export function createLatestRequest() {
  let current: AbortController | null = null;
  return {
    start() {
      current?.abort();
      current = new AbortController();
      return current;
    },
    isCurrent(controller: AbortController) {
      return current === controller && !controller.signal.aborted;
    },
    cancel() {
      current?.abort();
      current = null;
    },
  };
}

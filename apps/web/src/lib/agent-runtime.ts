export function conversationHistoryUrl(threadId: string): string {
  return `/api/agent/history?${new URLSearchParams({ session_id: threadId, limit: "100" })}`;
}

export function conversationRuntimeKey(threadId: string | undefined, draftId: string | undefined): string {
  return threadId ?? `draft:${draftId ?? "missing"}`;
}

export function historyMessageStatus(runStatus: string) {
  if (runStatus === "COMPLETED") return { type: "complete" as const, reason: "stop" as const };
  return {
    type: "incomplete" as const,
    reason: runStatus === "CANCELLED" ? "cancelled" as const : runStatus === "ERROR" ? "error" as const : "other" as const,
  };
}

export function activeConversationRun(runs: Array<{ run_id: string; status: string }> | undefined) {
  return runs?.find(run => !["COMPLETED", "CANCELLED", "ERROR", "REGENERATED"].includes(run.status)) ?? null;
}

const pendingSends = new Map<string, { id: string; text: string }>();
const activeRuns = new Map<string, string>();

export function registerConversationRun(threadId: string, runId: string): void {
  activeRuns.set(threadId, runId);
}

export async function cancelConversationRun(threadId: string, runId = activeRuns.get(threadId)): Promise<void> {
  if (!runId) throw new Error("尚未确认运行标识，请读取历史后停止。");
  const response = await fetch(`/api/agent/conversations/${encodeURIComponent(threadId)}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_id: runId }),
    signal: AbortSignal.timeout(20_000),
  });
  if (!response.ok) throw new Error("停止结果未确认，请重新读取运行状态。");
}

export function queueConversationSend(owner: string, id: string, text: string): void {
  pendingSends.set(owner, { id, text });
}

export function takeConversationSend(owner: string, id: string): string | undefined {
  const pending = pendingSends.get(owner);
  if (pending?.id !== id) return;
  pendingSends.delete(owner);
  return pending.text;
}

export function requireFinishedStream(response: Response): Response {
  if (!response.body) throw new Error("Agent 未返回运行流，请核对已保存内容。");
  const decoder = new TextDecoder();
  let pending = "";
  let terminal = false;
  return new Response(response.body.pipeThrough(new TransformStream<Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      pending += decoder.decode(chunk, { stream: true }).replace(/\r\n/g, "\n");
      let boundary = pending.indexOf("\n\n");
      while (boundary >= 0) {
        const block = pending.slice(0, boundary);
        pending = pending.slice(boundary + 2);
        const data = block.split("\n").filter(line => line.startsWith("data:")).map(line => line.slice(5).trimStart()).join("\n");
        if (data) {
          const event = JSON.parse(data) as { type: string };
          terminal ||= event.type === "RUN_FINISHED" || event.type === "RUN_ERROR";
        }
        boundary = pending.indexOf("\n\n");
      }
      controller.enqueue(chunk);
    },
    flush() {
      if (!terminal) throw new Error("连接已中断，运行结果未确认。请重新读取历史，勿直接重复发送。");
    },
  })), { status: response.status, headers: response.headers });
}

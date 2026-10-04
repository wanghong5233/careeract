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

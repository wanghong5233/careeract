import type { ThreadMessageLike } from "@assistant-ui/react";
import type { HistoryMessage, RunActivity } from "@/lib/agent-conversations";
import { historyMessageStatus, unansweredRunStatuses } from "@/lib/agent-runtime";

export function historyThreadMessages(messages: HistoryMessage[], runs?: Array<{ run_id: string; status: string }>): ThreadMessageLike[] {
  const unanswered = unansweredRunStatuses(runs, messages);
  const statuses = new Map((runs ?? []).map(run => [run.run_id, run.status]));
  const pending = new Map(unanswered.map(run => [run.run_id, { run_id: run.run_id, status: statuses.get(run.run_id)! }]));
  const statusMessage = (run: { run_id: string; status: string }): ThreadMessageLike => ({
    id: `run-status:${run.run_id}`, role: "assistant", content: "",
    status: historyMessageStatus(run.status),
    metadata: { custom: { runStatus: run.status, noSavedReply: true } },
  });
  const converted: ThreadMessageLike[] = [];
  const timedRuns = new Set<string>();
  messages.forEach((message, index) => {
    const showDuration = !message.run_id || !timedRuns.has(message.run_id);
    converted.push({
      id: message.id, role: message.role, content: message.content, createdAt: new Date(message.created_at * 1000),
      ...(message.role === "assistant" ? { status: historyMessageStatus(message.run_status), metadata: { custom: { messageCreatedAt: message.created_at > 0 ? message.created_at * 1000 : undefined, runStatus: message.run_status, runId: message.run_id, runDurationSeconds: showDuration ? message.run_duration_seconds : undefined, runProcess: message.process, noSavedReply: message.content ? undefined : true } } } : {}),
    });
    if (message.role === "assistant" && message.run_id) timedRuns.add(message.run_id);
    const run = message.run_id ? pending.get(message.run_id) : undefined;
    if (run && message.role === "user" && !messages.slice(index + 1).some(item => item.role === "user" && item.run_id === run.run_id)) {
      converted.push(statusMessage(run));
      pending.delete(run.run_id);
    }
  });
  pending.forEach(run => converted.push(statusMessage(run)));
  return converted;
}

export function groupLiveAssistantMessages(messages: readonly ThreadMessageLike[]): ThreadMessageLike[] {
  const result: ThreadMessageLike[] = [];
  let turn: ThreadMessageLike[] = [];
  const flush = () => {
    if (!turn.length) return;
    const final = turn.at(-1)!;
    const process: RunActivity[] = [];
    let finalText = "";
    for (const message of turn) {
      const parts = typeof message.content === "string" ? [{ type: "text" as const, text: message.content }] : message.content ?? [];
      const text = parts.filter(part => part.type === "text").map(part => part.text).join("\n");
      const hasTools = parts.some(part => part.type === "tool-call");
      const saved = message.metadata?.custom?.runProcess;
      if (Array.isArray(saved)) process.push(...saved as RunActivity[]);
      if (message !== final || hasTools) {
        if (text) process.push({ id: message.id ?? `process-${process.length}`, kind: "message", content: text });
      } else finalText = text;
      for (const part of parts) {
        if (part.type !== "tool-call") continue;
        const projected = part.result && typeof part.result === "object" ? part.result as Partial<RunActivity> : undefined;
        process.push({ id: part.toolCallId ?? `tool-${process.length}`, kind: "tool", label: part.toolName, status: projected?.status ?? (final.status?.type === "running" ? "RUNNING" : final.status?.type === "incomplete" && final.status.reason === "cancelled" ? "CANCELLED" : "UNKNOWN"), duration_seconds: projected?.duration_seconds });
      }
    }
    result.push({ ...final, content: finalText, metadata: { ...final.metadata, custom: { ...final.metadata?.custom, messageCreatedAt: final.metadata?.custom?.messageCreatedAt ?? final.createdAt?.getTime(), runProcess: Array.from(new Map(process.map(item => [item.id, item])).values()) } } });
    turn = [];
  };
  for (const message of messages) {
    if (message.role === "assistant") turn.push(message);
    else { flush(); result.push(message); }
  }
  flush();
  return result;
}

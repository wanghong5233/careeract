import type { ThreadMessageLike } from "@assistant-ui/react";
import type { HistoryMessage } from "@/lib/agent-conversations";
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
      ...(message.role === "assistant" ? { status: historyMessageStatus(message.run_status), metadata: { custom: { runStatus: message.run_status, runId: message.run_id, runDurationSeconds: showDuration ? message.run_duration_seconds : undefined } } } : {}),
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

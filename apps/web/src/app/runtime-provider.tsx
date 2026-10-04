"use client";

import { HttpAgent } from "@ag-ui/client";
import { ExportedMessageRepository, type ThreadHistoryAdapter } from "@assistant-ui/core";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useAgUiRuntime } from "@assistant-ui/react-ag-ui";
import { type ReactNode, useMemo, useState } from "react";

import { isRestrictedResponse, restrictedContentMessage } from "@/lib/privacy";
import { conversationHistoryUrl, historyMessageStatus, registerConversationRun, requireFinishedStream } from "@/lib/agent-runtime";

const AGENT_BFF_URL = "/api/agent";

export function RuntimeProvider({ children, agentThreadId }: Readonly<{ children: ReactNode; agentThreadId?: string }>) {
  const [fallbackThreadId] = useState(() => crypto.randomUUID());
  const threadId = agentThreadId ?? fallbackThreadId;
  const agent = useMemo(
    () =>
      new HttpAgent({
        url: AGENT_BFF_URL,
        threadId,
        headers: { Accept: "text/event-stream" },
        fetch: async (url, init) => {
          let requestInit = init;
          if (typeof init?.body === "string") {
            const body = JSON.parse(init.body) as { runId: string; messages?: Array<{ id: string; role: string; content?: string }> };
            registerConversationRun(threadId, body.runId);
            if (body.messages) {
              body.messages = body.messages
                .filter(message => ["user", "assistant"].includes(message.role) && typeof message.content === "string" && message.content.length > 0)
                .map(message => ({ id: message.id, role: message.role, content: message.content! }));
            }
            requestInit = { ...init, body: JSON.stringify(body) };
          }
          const response = await fetch(url, requestInit);
          if (response.status === 422 && await isRestrictedResponse(response)) {
            throw new Error(restrictedContentMessage);
          }
          if (!response.ok) {
            const messages: Record<number, string> = {
              401: "登录已失效，请重新登录后继续。",
              403: "无法验证请求，请从 CareerAct Agent 重试。",
              404: "找不到当前对话，请重新读取目录。",
              409: "本次请求已受理或当前对话仍有运行。请核对历史，勿重复发送。",
              413: "委托内容过大，请精简后重试。",
              415: "Agent 当前仅接收文本，请调整输入后重试。",
              422: "Agent 当前仅接收文本；附件和自定义上下文尚未开放。",
            };
            throw new Error(messages[response.status] ?? "Agent 暂时无法回应，未能确认本次工作结果。请核对已保存内容后重试。");
          }
          return requireFinishedStream(response);
        },
      }),
    [threadId],
  );
  const history = useMemo<ThreadHistoryAdapter>(() => ({
    async load() {
      if (!agentThreadId) return { messages: [] };
      const response = await fetch(conversationHistoryUrl(threadId), { cache: "no-store", signal: AbortSignal.timeout(20_000) });
      if (!response.ok) throw new Error("Agent 历史暂时无法读取，请稍后重试。");
      const body = await response.json() as { messages: Array<{ id: string; role: "user" | "assistant"; content: string; created_at: number; run_status: string }> };
      const messages = body.messages.map(message => ({
        id: message.id,
        role: message.role,
        content: message.content,
        createdAt: new Date(message.created_at * 1000),
        ...(message.role === "assistant" ? { status: historyMessageStatus(message.run_status) } : {}),
      }));
      return ExportedMessageRepository.fromBranchableArray(
        messages.map((message, index) => ({ message, parentId: index > 0 ? messages[index - 1]!.id : null })),
      );
    },
    async append() {},
    async update() {},
  }), [threadId, agentThreadId]);
  const runtime = useAgUiRuntime({ agent, adapters: { history } });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}

"use client";

import { HttpAgent } from "@ag-ui/client";
import { ExportedMessageRepository, type ThreadHistoryAdapter } from "@assistant-ui/core";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useAgUiRuntime } from "@assistant-ui/react-ag-ui";
import { type ReactNode, useMemo, useState } from "react";

import { isRestrictedResponse, restrictedContentMessage } from "@/lib/privacy";

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
            const body = JSON.parse(init.body) as { messages?: Array<{ id: string; role: string; content?: string }> };
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
          return response;
        },
      }),
    [threadId],
  );
  const history = useMemo<ThreadHistoryAdapter>(() => ({
    async load() {
      const response = await fetch("/api/agent/history", { cache: "no-store" });
      if (response.status === 404) return { messages: [] };
      if (!response.ok) throw new Error("伙伴历史暂时无法读取，请稍后重试。");
      const body = await response.json() as { messages: Array<{ id: string; role: "user" | "assistant"; content: string; created_at: number }> };
      const messages = body.messages.map(message => ({
        id: message.id,
        role: message.role,
        content: message.content,
        createdAt: new Date(message.created_at * 1000),
        ...(message.role === "assistant" ? { status: { type: "complete" as const, reason: "stop" as const } } : {}),
      }));
      return ExportedMessageRepository.fromBranchableArray(
        messages.map((message, index) => ({ message, parentId: index > 0 ? messages[index - 1]!.id : null })),
      );
    },
    async append() {},
    async update() {},
  }), []);
  const runtime = useAgUiRuntime({ agent, adapters: { history } });

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}

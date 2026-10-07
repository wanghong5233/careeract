"use client";

import { HttpAgent } from "@ag-ui/client";
import { ExportedMessageRepository, type ThreadHistoryAdapter } from "@assistant-ui/core";
import { AssistantRuntimeProvider } from "@assistant-ui/react";
import { useAgUiRuntime } from "@assistant-ui/react-ag-ui";
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";

import { isRestrictedResponse, restrictedContentMessage } from "@/lib/privacy";
import { registerConversationRun, requireFinishedStream } from "@/lib/agent-runtime";
import { historyThreadMessages } from "@/lib/conversation-presentation";
import { readConversationHistory } from "@/lib/agent-conversations";

const AGENT_BFF_URL = "/api/agent";

export function RuntimeProvider({ children, agentThreadId, threadKey }: Readonly<{ children: ReactNode; agentThreadId?: string; threadKey?: string }>) {
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
      const body = await readConversationHistory(threadId, AbortSignal.timeout(20_000));
      const messages = historyThreadMessages(body.messages, body.runs);
      return ExportedMessageRepository.fromBranchableArray(
        messages.map((message, index) => ({ message, parentId: index > 0 ? messages[index - 1]!.id ?? null : null })),
      );
    },
    async append() {},
    async update() {},
  }), [threadId, agentThreadId]);
  const runtime = useAgUiRuntime({ agent, adapters: { history } });

  const sessionKey = threadKey ?? agentThreadId ?? threadId;
  const activeSessionRef = useRef(sessionKey);
  const runtimeRef = useRef(runtime);
  useEffect(() => {
    runtimeRef.current = runtime;
  }, [runtime]);
  useEffect(() => {
    if (activeSessionRef.current === sessionKey) return;
    activeSessionRef.current = sessionKey;
    const controller = new AbortController();
    runtimeRef.current.thread.reset();
    if (agentThreadId) {
      void readConversationHistory(threadId, controller.signal)
        .then(body => {
          if (controller.signal.aborted || activeSessionRef.current !== sessionKey) return;
          runtimeRef.current.thread.reset(historyThreadMessages(body.messages, body.runs));
        })
        .catch(error => { if (error.name !== "AbortError") console.error(error); });
    }
    return () => controller.abort();
  }, [agentThreadId, sessionKey, threadId]);

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      {children}
    </AssistantRuntimeProvider>
  );
}

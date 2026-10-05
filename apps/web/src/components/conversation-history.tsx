"use client";

import { useMemo } from "react";
import { AssistantRuntimeProvider, useExternalStoreRuntime, type ThreadMessageLike } from "@assistant-ui/react";
import { ConversationMessages } from "@/components/conversation-messages";
import type { HistoryMessage } from "@/lib/agent-conversations";
import { historyThreadMessages } from "@/lib/conversation-presentation";

export function ConversationHistory({ messages, runs, liveMessages, isRunning = false }: { messages: HistoryMessage[]; runs?: Array<{ run_id: string; status: string }>; liveMessages?: readonly ThreadMessageLike[]; isRunning?: boolean }) {
  const converted = useMemo(() => historyThreadMessages(messages, runs), [messages, runs]);
  const displayed = useMemo(() => {
    if (!liveMessages) return converted;
    const saved = new Map(converted.map(message => [message.id, message]));
    return liveMessages.map(message => ({ ...message, metadata: { ...message.metadata, custom: { ...saved.get(message.id)?.metadata?.custom, ...message.metadata?.custom } } }));
  }, [converted, liveMessages]);
  const runtime = useExternalStoreRuntime<ThreadMessageLike>({ messages: displayed, convertMessage: message => message, isRunning, onNew: async () => { throw new Error("消息视图只读。"); } });
  return <AssistantRuntimeProvider runtime={runtime}><ConversationMessages /></AssistantRuntimeProvider>;
}

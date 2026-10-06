"use client";

import { useMemo } from "react";
import { AssistantRuntimeProvider, useExternalStoreRuntime, type ThreadMessageLike } from "@assistant-ui/react";
import { ConversationMessages } from "@/components/conversation-messages";
import { MessageActionsContext, type MessageEdit, type MessageFeedbackHandler } from "@/components/message-actions";
import type { HistoryMessage } from "@/lib/agent-conversations";
import { historyThreadMessages, groupLiveAssistantMessages } from "@/lib/conversation-presentation";

export function ConversationHistory({ messages, runs, liveMessages, isRunning = false, onQuote, onAddToConversation, onEdit, editing, onBranch, onFeedback }: { messages: HistoryMessage[]; runs?: Array<{ run_id: string; status: string }>; liveMessages?: readonly ThreadMessageLike[]; isRunning?: boolean; onQuote?: (id: string, text: string) => void; onAddToConversation?: (text: string) => void; onEdit?: (id: string, text: string) => void; editing?: MessageEdit; onBranch?: (id: string) => void; onFeedback?: MessageFeedbackHandler }) {
  const converted = useMemo(() => historyThreadMessages(messages, runs), [messages, runs]);
  const displayed = useMemo(() => {
    if (!liveMessages) return converted;
    const groupedLive = groupLiveAssistantMessages(liveMessages);
    const saved = new Map(converted.map(message => [message.id, message]));
    const combined = new Map(converted.map(message => [message.id, message]));
    const text = (message: ThreadMessageLike) => typeof message.content === "string" ? message.content : (message.content ?? []).filter(part => part.type === "text").map(part => part.text).join("\n");
    let restoredPrefix = 0;
    while (restoredPrefix < converted.length && restoredPrefix < groupedLive.length) {
      const restored = groupedLive[restoredPrefix];
      const canonical = converted[restoredPrefix];
      if (restored.role !== canonical.role || restored.status?.type === "running" || text(restored) !== text(canonical)) break;
      restoredPrefix++;
    }
    if (!converted.slice(0, restoredPrefix).some(message => message.role === "assistant")) restoredPrefix = 0;
    groupedLive.forEach((incoming, index) => {
      const message = index < restoredPrefix ? { ...incoming, id: converted[index].id } : incoming;
      const persisted = saved.get(message.id);
      const terminal = ["COMPLETED", "CANCELLED", "ERROR", "REGENERATED", "INTERRUPTED"].includes(String(persisted?.metadata?.custom?.runStatus));
      combined.set(message.id, {
        ...message,
        ...(terminal ? { status: persisted?.status } : {}),
        metadata: { ...message.metadata, custom: terminal ? { ...message.metadata?.custom, ...persisted?.metadata?.custom } : { ...persisted?.metadata?.custom, ...message.metadata?.custom } },
      });
    });
    return Array.from(combined.values());
  }, [converted, liveMessages]);
  const runtime = useExternalStoreRuntime<ThreadMessageLike>({ messages: displayed, convertMessage: message => message, isRunning, onNew: async () => { throw new Error("消息视图只读。"); } });
  return <MessageActionsContext.Provider value={{ quote: onQuote, addToConversation: onAddToConversation, edit: onEdit, editId: messages.findLast(message => message.role === "user")?.id, editing, branch: onBranch, feedback: onFeedback }}><AssistantRuntimeProvider runtime={runtime}><ConversationMessages /></AssistantRuntimeProvider></MessageActionsContext.Provider>;
}

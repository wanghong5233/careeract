"use client";

import { useMemo } from "react";
import { AssistantRuntimeProvider, MessagePrimitive, ThreadPrimitive, useExternalStoreRuntime, type ThreadMessageLike } from "@assistant-ui/react";
import { MarkdownText } from "@/components/markdown-text";
import type { HistoryMessage } from "@/lib/agent-conversations";
import { unansweredRunStatuses } from "@/lib/agent-runtime";
import styles from "./agent-space.module.css";

export function ConversationHistory({ messages, runs }: { messages: HistoryMessage[]; runs?: Array<{ run_id: string; status: string }> }) {
  const converted = useMemo<ThreadMessageLike[]>(() => messages.map(message => ({
    id: message.id, role: message.role, content: message.content, createdAt: new Date(message.created_at * 1000),
    ...(message.role === "assistant" ? { status: message.run_status === "COMPLETED"
      ? { type: "complete" as const, reason: "stop" as const }
      : { type: "incomplete" as const, reason: message.run_status === "CANCELLED" ? "cancelled" as const : message.run_status === "ERROR" ? "error" as const : "other" as const } } : {}),
  })), [messages]);
  const runtime = useExternalStoreRuntime({ messages: converted, convertMessage: message => message, isRunning: false, onNew: async () => { throw new Error("历史视图只读。"); } });
  return <AssistantRuntimeProvider runtime={runtime}><ThreadPrimitive.Root className={`${styles.messageThread} mx-auto w-full max-w-[704px] space-y-8 py-6`}>
    <ThreadPrimitive.Messages components={{ UserMessage: HistoryUserMessage, AssistantMessage: HistoryAssistantMessage }} />
    {messages.filter(message => message.role === "assistant" && message.run_status !== "COMPLETED").map(message => <p key={message.id} role="status" className={`${styles.messageStatus} ${message.run_status === "ERROR" ? styles.messageStatusError : styles.messageStatusIncomplete}`}>{message.run_status === "CANCELLED" ? "已取消" : message.run_status === "ERROR" ? "运行失败" : message.run_status === "PAUSED" ? "等待继续" : message.run_status === "RUNNING" || message.run_status === "PENDING" ? "运行尚未结束" : "运行状态未确认"} · 显示已保存内容</p>)}
    {unansweredRunStatuses(runs, messages).map(run => <p key={run.run_id} role="status" className={`${styles.messageStatus} ${styles.messageStatusError}`}>{run.label} · 本次运行没有已保存的回复</p>)}
  </ThreadPrimitive.Root></AssistantRuntimeProvider>;
}

function HistoryUserMessage() {
  return <MessagePrimitive.Root className={styles.userMessage}><MessagePrimitive.Content /></MessagePrimitive.Root>;
}

function HistoryAssistantMessage() {
  return <MessagePrimitive.Root className={styles.assistantMessage}><MessagePrimitive.Content components={{ Text: MarkdownText }} /></MessagePrimitive.Root>;
}

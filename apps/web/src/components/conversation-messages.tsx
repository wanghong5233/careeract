"use client";

import type { ReactNode } from "react";
import { ArrowDown } from "lucide-react";
import { MessagePrimitive, ThreadPrimitive, useAuiState } from "@assistant-ui/react";
import { MarkdownText } from "@/components/markdown-text";
import { TooltipIconButton } from "@/components/tooltip-icon-button";
import { cn } from "@/lib/utils";
import styles from "./agent-space.module.css";

export function ConversationMessages({ children }: { children?: ReactNode }) {
  const waiting = useAuiState(state => state.thread.isRunning && state.thread.messages.at(-1)?.role !== "assistant");
  return <ThreadPrimitive.Root className={styles.threadRoot}>
    <ThreadPrimitive.Viewport className={styles.messageViewport}>
      <div className={styles.messageThread}>
        <ThreadPrimitive.Messages components={{ UserMessage: ConversationUserMessage, AssistantMessage: ConversationAssistantMessage }} />
        {waiting && <p role="status" className={cn(styles.messageStatus, styles.messageStatusRunning)}><span aria-hidden="true" className={styles.streamingIndicator} />正在等待回复…</p>}
        {children}
      </div>
      <ThreadPrimitive.ViewportFooter className={styles.scrollFooter}>
        <ThreadPrimitive.ScrollToBottom asChild><TooltipIconButton tooltip="返回最新消息" aria-label="返回最新消息" side="top" className={styles.scrollToBottom}><ArrowDown /></TooltipIconButton></ThreadPrimitive.ScrollToBottom>
      </ThreadPrimitive.ViewportFooter>
    </ThreadPrimitive.Viewport>
  </ThreadPrimitive.Root>;
}

export function ConversationUserMessage() {
  return <MessagePrimitive.Root className={styles.userMessage}><MessagePrimitive.Content /></MessagePrimitive.Root>;
}

export function ConversationAssistantMessage() {
  const status = useAuiState(state => state.message.status);
  const runStatus = useAuiState(state => state.message.metadata.custom.runStatus);
  const noSavedReply = useAuiState(state => state.message.metadata.custom.noSavedReply === true);
  const hasText = useAuiState(state => state.message.content.some(part => part.type === "text" && part.text.length > 0));
  const running = status?.type === "running";
  const incomplete = status?.type === "incomplete";
  const reason = incomplete ? status.reason : undefined;
  const label = reason === "cancelled" ? "已取消" : reason === "error" ? "运行失败" : runStatus === "PAUSED" ? "等待继续" : ["RUNNING", "PENDING"].includes(String(runStatus)) ? "运行尚未结束" : "运行状态未确认";
  return <MessagePrimitive.Root className={styles.assistantMessage}>
    {hasText && <MessagePrimitive.Content components={{ Text: MarkdownText }} />}
    {running && <p role="status" className={cn(styles.messageStatus, styles.messageStatusRunning)}><span aria-hidden="true" className={styles.streamingIndicator} />{hasText ? "正在生成…" : "正在等待回复…"}</p>}
    {incomplete && <p role="status" className={cn(styles.messageStatus, reason === "error" ? styles.messageStatusError : styles.messageStatusIncomplete)}>{label} · {noSavedReply ? "本次运行没有已保存的回复" : "请核对已显示内容"}</p>}
  </MessagePrimitive.Root>;
}

"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowDown, Check, Copy, GitBranch, Pencil } from "lucide-react";
import { ActionBarPrimitive, MessagePrimitive, SelectionToolbarPrimitive, ThreadPrimitive, useAuiState } from "@assistant-ui/react";
import { MarkdownText } from "@/components/markdown-text";
import { TooltipIconButton } from "@/components/tooltip-icon-button";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { formatRunDuration } from "@/lib/run-presentation";
import { useMessageActions } from "@/components/message-actions";
import styles from "./agent-space.module.css";

export function ConversationMessages({ children }: { children?: ReactNode }) {
  const viewport = useRef<HTMLDivElement>(null);
  const waiting = useAuiState(state => state.thread.isRunning && state.thread.messages.at(-1)?.role !== "assistant");
  const startedAt = useAuiState(state => state.thread.messages.findLast(message => message.role === "user")?.createdAt?.getTime());
  return <ThreadPrimitive.Root className={styles.threadRoot}>
    <PromptNavigation viewport={viewport} />
    <ThreadPrimitive.Viewport ref={viewport} className={styles.messageViewport}>
      <div className={styles.messageThread}>
        <ThreadPrimitive.Messages components={{ UserMessage: ConversationUserMessage, AssistantMessage: ConversationAssistantMessage }} />
        <MessageSelectionToolbar />
        {waiting && <div><RunElapsed startedAt={startedAt} running /><p role="status" className={cn(styles.messageStatus, styles.messageStatusRunning)}><span aria-hidden="true" className={styles.streamingIndicator} />正在等待回复…</p></div>}
        {children}
      </div>
      <ThreadPrimitive.ViewportFooter className={styles.scrollFooter}>
        <ThreadPrimitive.ScrollToBottom asChild><TooltipIconButton tooltip="返回最新消息" aria-label="返回最新消息" side="top" className={styles.scrollToBottom}><ArrowDown /></TooltipIconButton></ThreadPrimitive.ScrollToBottom>
      </ThreadPrimitive.ViewportFooter>
    </ThreadPrimitive.Viewport>
  </ThreadPrimitive.Root>;
}

function MessageSelectionToolbar() {
  const actions = useMessageActions();
  const addToConversation = actions.addToConversation;
  if (!addToConversation) return null;
  return <SelectionToolbarPrimitive.Root className={styles.selectionToolbar} role="toolbar" aria-label="选中文字操作">
    <Button type="button" variant="ghost" size="sm" onClick={() => runSelectionAction(addToConversation)}>添加到对话</Button>
    {actions.quote && <Button type="button" variant="ghost" size="sm" onClick={() => runSelectionAction((text, id) => actions.quote?.(id, text))}>在侧边聊天中提问</Button>}
  </SelectionToolbarPrimitive.Root>;
}

function runSelectionAction(action: (text: string, id: string) => void) {
  const selection = window.getSelection();
  const text = selection?.toString().trim() ?? "";
  const node = selection?.anchorNode instanceof Element ? selection.anchorNode : selection?.anchorNode?.parentElement;
  const message = node?.closest<HTMLElement>("[data-message-id]");
  const region = node?.closest<HTMLElement>('[data-aui-quote-selectable="true"]');
  if (!text || !message?.dataset.messageId || !region || !selection?.focusNode || !region.contains(selection.focusNode)) return;
  action(text, message.dataset.messageId);
  selection?.removeAllRanges();
}

export function ConversationUserMessage() {
  const actions = useMessageActions();
  const id = useAuiState(state => state.message.id);
  const original = useAuiState(state => state.message.content.filter(part => part.type === "text").map(part => part.text).join("\n"));
  const copied = useAuiState(state => state.message.isCopied);
  return <MessagePrimitive.Root className={styles.userTurn} data-prompt-id={id} data-aui-quote-selectable="false">
    <div className={styles.userMessage}><MessagePrimitive.Content /></div>
    <ActionBarPrimitive.Root className={styles.userActions}>
      <ActionBarPrimitive.Copy asChild><TooltipIconButton tooltip={copied ? "已复制" : "复制消息"} aria-label={copied ? "已复制" : "复制消息"}>{copied ? <Check /> : <Copy />}</TooltipIconButton></ActionBarPrimitive.Copy>
      {actions.edit && actions.editId === id && <TooltipIconButton tooltip="编辑并另建分支" aria-label="编辑并另建分支" onClick={() => actions.edit?.(id, original)}><Pencil /></TooltipIconButton>}
      <span role="status" className="sr-only">{copied ? "消息已复制" : ""}</span>
    </ActionBarPrimitive.Root>
  </MessagePrimitive.Root>;
}

function PromptNavigation({ viewport }: { viewport: React.RefObject<HTMLDivElement | null> }) {
  const messages = useAuiState(state => state.thread.messages);
  const prompts = messages.filter(message => message.role === "user");
  const promptIds = prompts.map(message => message.id).join("\0");
  const [active, setActive] = useState<string | null>(null);
  useEffect(() => {
    const container = viewport.current;
    if (!container) return;
    const update = () => {
      const boundary = container.getBoundingClientRect().top + 80;
      const elements = Array.from(container.querySelectorAll<HTMLElement>("[data-prompt-id]"));
      const current = elements.findLast(element => element.getBoundingClientRect().top <= boundary) ?? elements[0];
      setActive(current?.dataset.promptId ?? null);
    };
    const observer = new ResizeObserver(update);
    observer.observe(container);
    if (container.firstElementChild) observer.observe(container.firstElementChild);
    container.addEventListener("scroll", update, { passive: true });
    update();
    return () => { observer.disconnect(); container.removeEventListener("scroll", update); };
  }, [promptIds, viewport]);
  if (prompts.length < 2) return null;
  return <nav aria-label="对话轮次导航" className={styles.promptNavigation}>
    {prompts.map((message, index) => {
      const text = message.content.filter(part => part.type === "text").map(part => part.text).join("\n");
      return <TooltipIconButton key={message.id} className={styles.promptTick} tooltip={text.length > 300 ? `${text.slice(0, 300)}…` : text} side="right" aria-label={`跳到第 ${index + 1} 条消息`} aria-current={active === message.id ? "location" : undefined} onClick={() => {
        const target = Array.from(viewport.current?.querySelectorAll<HTMLElement>("[data-prompt-id]") ?? []).find(element => element.dataset.promptId === message.id);
        target?.scrollIntoView({ block: "start", behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
        setActive(message.id);
      }}><span aria-hidden="true" /></TooltipIconButton>;
    })}
  </nav>;
}

export function ConversationAssistantMessage() {
  const actions = useMessageActions();
  const id = useAuiState(state => state.message.id);
  const duration = useAuiState(state => state.message.metadata.custom.runDurationSeconds);
  const startedAt = useAuiState(state => state.thread.messages.findLast(message => message.role === "user")?.createdAt?.getTime());
  const status = useAuiState(state => state.message.status);
  const runStatus = useAuiState(state => state.message.metadata.custom.runStatus);
  const noSavedReply = useAuiState(state => state.message.metadata.custom.noSavedReply === true);
  const hasText = useAuiState(state => state.message.content.some(part => part.type === "text" && part.text.length > 0));
  const running = status?.type === "running";
  const incomplete = status?.type === "incomplete";
  const reason = incomplete ? status.reason : undefined;
  const label = runStatus === "INTERRUPTED" ? "运行中断 · 结果未知" : reason === "cancelled" ? "已取消" : reason === "error" ? "运行失败" : runStatus === "PAUSED" ? "等待继续" : ["RUNNING", "PENDING"].includes(String(runStatus)) ? "运行尚未结束" : "运行状态未确认";
  return <MessagePrimitive.Root className={styles.assistantMessage} data-message-id={id} data-aui-quote-selectable="false">
    <RunElapsed duration={duration} startedAt={startedAt} running={running} />
    {hasText && <div data-aui-quote-selectable={actions.addToConversation ? "true" : "false"}><MessagePrimitive.Content components={{ Text: MarkdownText }} /></div>}
    {running && <p role="status" className={cn(styles.messageStatus, styles.messageStatusRunning)}><span aria-hidden="true" className={styles.streamingIndicator} />{hasText ? "正在生成…" : "正在等待回复…"}</p>}
    {incomplete && <p role="status" className={cn(styles.messageStatus, reason === "error" ? styles.messageStatusError : styles.messageStatusIncomplete)}>{label} · {noSavedReply ? "本次运行没有已保存的回复" : "请核对已显示内容"}</p>}
    {actions.branch && hasText && runStatus === "COMPLETED" && <div className={styles.assistantActions}>
      <TooltipIconButton tooltip="从此处创建独立分支" aria-label="从此处创建独立分支" onClick={() => actions.branch?.(id)}><GitBranch /></TooltipIconButton>
    </div>}
  </MessagePrimitive.Root>;
}

export function RunElapsed({ duration, startedAt, running = false }: { duration?: unknown; startedAt?: number; running?: boolean }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running || startedAt === undefined) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running, startedAt]);
  const label = running && startedAt !== undefined ? formatRunDuration(Math.max(0, (now - startedAt) / 1000)) : formatRunDuration(duration);
  return label ? <p className={styles.runElapsed}>{running ? "本页计时" : "用时"} {label}</p> : null;
}

"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowDown, Check, ChevronRight, Copy, GitFork, Pencil, ThumbsDown, ThumbsUp, Wrench } from "lucide-react";
import { ActionBarPrimitive, MessagePrimitive, SelectionToolbarPrimitive, ThreadPrimitive, useAuiState } from "@assistant-ui/react";
import { MarkdownText } from "@/components/markdown-text";
import { TooltipIconButton } from "@/components/tooltip-icon-button";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import type { RunActivity } from "@/lib/agent-conversations";
import { cn } from "@/lib/utils";
import { formatMessageTimestamp, formatRunDuration } from "@/lib/run-presentation";
import { useMessageActions, type MessageEdit } from "@/components/message-actions";
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
  const editing = actions.editing?.id === id ? actions.editing : undefined;
  return <MessagePrimitive.Root className={cn(styles.userTurn, editing && styles.editingTurn)} data-prompt-id={id} data-aui-quote-selectable="false">
    {editing ? <MessageEditForm editing={editing} /> : <><div className={styles.userMessage}><MessagePrimitive.Content /></div>
    <ActionBarPrimitive.Root className={styles.userActions}>
      <ActionBarPrimitive.Copy asChild><TooltipIconButton tooltip={copied ? "已复制" : "复制消息"} aria-label={copied ? "已复制" : "复制消息"}>{copied ? <Check /> : <Copy />}</TooltipIconButton></ActionBarPrimitive.Copy>
      {actions.edit && actions.editId === id && <TooltipIconButton tooltip="编辑消息" aria-label="编辑消息" onClick={() => actions.edit?.(id, original)}><Pencil /></TooltipIconButton>}
      <span role="status" className="sr-only">{copied ? "消息已复制" : ""}</span>
    </ActionBarPrimitive.Root></>}
  </MessagePrimitive.Root>;
}

export function MessageEditForm({ editing }: { editing: MessageEdit }) {
  return <form className={styles.messageEditor} onSubmit={event => { event.preventDefault(); if (!editing.busy && editing.text.trim()) editing.onSubmit(); }}>
    <textarea aria-label="修改后的消息" autoFocus rows={3} maxLength={4000} disabled={editing.busy} value={editing.text} onChange={event => editing.onChange(event.target.value)} onKeyDown={event => {
      if (event.nativeEvent.isComposing) return;
      if (event.key === "Escape" && !editing.busy) { event.preventDefault(); editing.onCancel(); }
      if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); event.currentTarget.form?.requestSubmit(); }
    }} />
    <p className={styles.editHint}>发送到独立分支，原对话及后续历史保留。</p>
    {editing.error && <p role="alert" className={styles.messageStatusError}>{editing.error}</p>}
    <div className={styles.editActions}>
      <Button type="button" variant="ghost" size="sm" disabled={editing.busy} onClick={editing.onCancel}>取消</Button>
      <Button type="submit" size="sm" disabled={editing.busy || !editing.text.trim()}>{editing.busy ? "正在创建…" : "发送到新分支"}</Button>
    </div>
  </form>;
}

function PromptNavigation({ viewport }: { viewport: React.RefObject<HTMLDivElement | null> }) {
  const messages = useAuiState(state => state.thread.messages);
  const running = useAuiState(state => state.thread.isRunning);
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
        target?.scrollIntoView({ block: "start", behavior: running || window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
        setActive(message.id);
      }}><span aria-hidden="true" /></TooltipIconButton>;
    })}
  </nav>;
}

export function ConversationAssistantMessage() {
  const actions = useMessageActions();
  const id = useAuiState(state => state.message.id);
  const duration = useAuiState(state => state.message.metadata.custom.runDurationSeconds);
  const copied = useAuiState(state => state.message.isCopied);
  const timestamp = useAuiState(state => state.message.metadata.custom.messageCreatedAt);
  const messageTime = formatMessageTimestamp(timestamp);
  const process = useAuiState(state => state.message.metadata.custom.runProcess as RunActivity[] | undefined);
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
    {process?.length ? <RunProcess process={process} duration={duration} startedAt={startedAt} running={running} /> : <RunElapsed duration={duration} startedAt={startedAt} running={running} />}
    {hasText && <div data-aui-quote-selectable={actions.addToConversation ? "true" : "false"}><MessagePrimitive.Content components={{ Text: MarkdownText }} /></div>}
    {running && <p role="status" className={cn(styles.messageStatus, styles.messageStatusRunning)}><span aria-hidden="true" className={styles.streamingIndicator} />{hasText ? "正在生成…" : "正在等待回复…"}</p>}
    {incomplete && <p role="status" className={cn(styles.messageStatus, reason === "error" ? styles.messageStatusError : styles.messageStatusIncomplete)}>{label} · {noSavedReply ? "本次运行没有已保存的回复" : "请核对已显示内容"}</p>}
    {hasText && !running && <ActionBarPrimitive.Root className={styles.assistantActions}>
      <ActionBarPrimitive.Copy asChild><TooltipIconButton tooltip={copied ? "已复制" : "复制回答"} aria-label={copied ? "已复制" : "复制回答"} side="top">{copied ? <Check /> : <Copy />}</TooltipIconButton></ActionBarPrimitive.Copy>
      {actions.feedback && runStatus === "COMPLETED" && <>
        <TooltipIconButton tooltip="回答有帮助" aria-label="回答有帮助" side="top" onClick={() => actions.feedback?.(id, "positive")}><ThumbsUp /></TooltipIconButton>
        <TooltipIconButton tooltip="回答需要改进" aria-label="回答需要改进" side="top" onClick={() => actions.feedback?.(id, "negative")}><ThumbsDown /></TooltipIconButton>
      </>}
      {actions.branch && runStatus === "COMPLETED" && <TooltipIconButton tooltip="分支到新聊天" aria-label="分支到新聊天" side="top" onClick={() => actions.branch?.(id)}><GitFork /></TooltipIconButton>}
      {messageTime && <time className={styles.messageTime} dateTime={messageTime.dateTime} title={messageTime.title}>{messageTime.label}</time>}
      <span role="status" className="sr-only">{copied ? "回答已复制" : ""}</span>
    </ActionBarPrimitive.Root>}
  </MessagePrimitive.Root>;
}

export function RunProcess({ process, duration, startedAt, running }: { process: RunActivity[]; duration?: unknown; startedAt?: number; running?: boolean }) {
  const labels: Record<string, string> = { RUNNING: "进行中", PENDING: "等待中", COMPLETED: "已完成", ERROR: "失败", REJECTED: "未执行", CANCELLED: "已取消", PAUSED: "等待确认", UNKNOWN: "结果未确认" };
  return <Collapsible className={styles.runProcess}>
    <CollapsibleTrigger className={styles.processTrigger} aria-label="运行过程">
      <RunElapsed duration={duration} startedAt={startedAt} running={running} />
      {!running && formatRunDuration(duration) === null && <span>运行过程</span>}
      {running && startedAt === undefined && <span>运行过程</span>}
      <ChevronRight aria-hidden="true" />
    </CollapsibleTrigger>
    <CollapsibleContent className={styles.processContent}>
      {process.map(item => item.kind === "message" ? <p key={item.id} className={styles.processMessage}>{item.content}</p> : <div key={item.id} className={styles.processTool}>
        <Wrench aria-hidden="true" /><span>{item.label ?? "工具调用"}</span><span className={item.status === "ERROR" ? styles.messageStatusError : undefined}>{labels[item.status ?? "UNKNOWN"] ?? labels.UNKNOWN}</span>
        {formatRunDuration(item.duration_seconds) !== null && <span>{formatRunDuration(item.duration_seconds)}</span>}
      </div>)}
    </CollapsibleContent>
  </Collapsible>;
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

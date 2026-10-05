"use client";

import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { ArrowUp, PanelRightClose, Square, X } from "lucide-react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { RuntimeProvider } from "@/app/runtime-provider";
import { ConversationHistory } from "@/components/conversation-history";
import { AgentComposerTools } from "@/components/agent-composer-tools";
import { Button } from "@/components/ui/button";
import { TooltipIconButton } from "@/components/tooltip-icon-button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useConversationHistory } from "@/hooks/use-conversation-history";
import { closeSideChat, createSideChat, saveConversation, type SideChat } from "@/lib/agent-conversations";
import { appendSideQuote, getSideChatStore } from "@/lib/side-chat-state";
import { cancelConversationRun, reconcileConversationRun } from "@/lib/agent-runtime";
import styles from "./agent-space.module.css";

export function useSideChat(owner: string, sourceId: string, persisted: boolean, mainCheckpoint: string | null) {
  const store = getSideChatStore(owner);
  const state = useSyncExternalStore(store.subscribe, store.snapshot, store.serverSnapshot);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [replacement, setReplacement] = useState<{ sourceId: string; messageId?: string; quote?: string } | null>(null);
  const pending = useRef<{ id: string; sourceId: string; messageId?: string; quote: string } | null>(null);
  const creating = useRef(false);
  async function open(messageId?: string, quote = "") {
    if (!persisted || creating.current) return;
    const latest = store.snapshot();
    if (latest.chat) {
      if (latest.chat.side_context.source_id !== sourceId) { setReplacement({ sourceId, messageId, quote }); return; }
      if (appendSideQuote(latest.draft, quote).length > 4000) { setError("引用与草稿超过 4000 字，请精简后再添加；草稿已保留。"); return; }
      store.update(previous => ({ ...previous, hidden: false, draft: appendSideQuote(previous.draft, quote) }));
      requestAnimationFrame(() => document.getElementById("career-side-input")?.focus());
      return;
    }
    creating.current = true;
    setBusy(true); setError("");
    if (!pending.current || pending.current.sourceId !== sourceId || pending.current.messageId !== messageId || pending.current.quote !== quote) pending.current = { id: crypto.randomUUID(), sourceId, messageId, quote };
    try {
      const chat = await createSideChat(pending.current.id, state.tabId, sourceId, messageId, quote);
      store.update(previous => ({ ...previous, chat, hidden: false, draft: "", mainCheckpoint }));
      pending.current = null;
    } catch (failure) { setError(failure instanceof Error ? failure.message : "侧聊创建结果未确认。"); }
    finally { creating.current = false; setBusy(false); }
  }
  return { store, state, busy, error, open, replacement, clearReplacement: () => setReplacement(null) };
}

export function SideChatPanel({ controller, mainCheckpoint }: { controller: ReturnType<typeof useSideChat>; mainCheckpoint: string | null }) {
  const { state, store, replacement } = controller;
  const chat = state.chat;
  if (!chat) return null;
  return <aside className={styles.sideChat} style={{ display: state.hidden ? "none" : undefined }} aria-label="临时侧聊">
    <RuntimeProvider key={chat.session_id} agentThreadId={chat.session_id}><SideChatContent chat={chat} store={store} mainCheckpoint={mainCheckpoint} replacement={replacement} clearReplacement={controller.clearReplacement} /></RuntimeProvider>
  </aside>;
}

function SideChatContent({ chat, store, mainCheckpoint, replacement, clearReplacement }: { chat: SideChat; store: ReturnType<typeof getSideChatStore>; mainCheckpoint: string | null; replacement: ReturnType<typeof useSideChat>["replacement"]; clearReplacement: () => void }) {
  const state = useSyncExternalStore(store.subscribe, store.snapshot, store.serverSnapshot);
  const history = useConversationHistory(chat.session_id, true);
  const aui = useAui();
  const running = useAuiState(value => value.thread.isRunning);
  const messages = useAuiState(value => value.thread.messages);
  const [sending, setSending] = useState(false);
  const [closing, setClosing] = useState(false);
  const [confirmClose, setConfirmClose] = useState(false);
  const [suppress, setSuppress] = useState(state.suppressCloseWarning);
  const [feedback, setFeedback] = useState("");
  const [stopping, setStopping] = useState(false);
  const wasRunning = useRef(false);
  const sendLock = useRef(false);
  const stopRequested = useRef(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const active = running || sending || !!history.activeRun;
  useEffect(() => { if (wasRunning.current && !running) void history.refresh(); wasRunning.current = running; }, [running, history]);
  useEffect(() => { if (!state.hidden) input.current?.focus(); }, [state.hidden]);
  async function stop() {
    stopRequested.current = true;
    setStopping(true); setFeedback("");
    try { await cancelConversationRun(chat.session_id, history.activeRun?.run_id); await history.refresh(); }
    catch (failure) { setFeedback(failure instanceof Error ? failure.message : "停止结果未确认。"); }
    finally { setStopping(false); }
  }
  async function discard() {
    if (closing) return;
    setClosing(true); setFeedback("");
    try {
      if (active) { await stop(); setFeedback("已请求停止，请等待服务端终态后再确认关闭；当前侧聊仍保留。"); return; }
      await closeSideChat(chat.session_id);
      store.update(previous => ({ ...previous, chat: null, hidden: true, draft: "", suppressCloseWarning: suppress }));
      setConfirmClose(false); clearReplacement();
      if (replacement) window.dispatchEvent(new CustomEvent("careeract:side-replace", { detail: replacement }));
    } catch (failure) { setFeedback(failure instanceof Error ? failure.message : "丢弃结果未确认，侧聊仍保留。"); }
    finally { setClosing(false); }
  }
  async function send() {
    if (sendLock.current || active || history.loading || history.error || !state.draft.trim()) return;
    sendLock.current = true; stopRequested.current = false; setSending(true); setFeedback("");
    const text = state.draft.trim();
    try {
      store.update(previous => ({ ...previous, mainCheckpoint }));
      await Promise.resolve(aui.thread.append({ role: "user", content: [{ type: "text", text }] }));
      if (!stopRequested.current) store.update(previous => previous.draft.trim() === text ? { ...previous, draft: "" } : previous);
    } catch (failure) { setFeedback(failure instanceof Error ? failure.message : "发送结果未确认，草稿仍保留。"); }
    finally { sendLock.current = false; setSending(false); }
  }
  const mustConfirm = active || !state.suppressCloseWarning;
  return <>
    <header className={styles.header}><span className="flex-1 truncate">临时侧聊</span><TooltipIconButton tooltip="收起并保留侧聊" aria-label="收起侧聊" onClick={() => store.update(previous => ({ ...previous, hidden: true }))}><PanelRightClose /></TooltipIconButton><TooltipIconButton tooltip="关闭并丢弃侧聊" aria-label="关闭侧聊" onClick={() => { if (mustConfirm) setConfirmClose(true); else void discard(); }}><X /></TooltipIconButton></header>
    <p className={styles.sideSource} title={chat.side_context.source_title}>来自 {chat.side_context.source_title} · {history.history?.session.project_id ? "来源项目" : "个人背景"}</p>
    {((mainCheckpoint && state.mainCheckpoint && mainCheckpoint !== state.mainCheckpoint) || replacement) && <p className={styles.sideSource}>主线有变化；下一次提问按需读取，当前回答不会自动更新。</p>}
    <div className={styles.startArea}>
      {history.loading && <p role="status" className={styles.feedback}>正在读取侧聊…</p>}
      {history.error && <div className={styles.feedback}><p role="alert">{history.error}</p><Button size="sm" variant="ghost" onClick={history.refresh}>重新读取侧聊</Button></div>}
      {chat.side_context.quote && !history.loading && !history.history?.messages.length && <blockquote className={styles.sideQuote}><ConversationHistory messages={[{ id: `quote:${chat.session_id}`, role: "assistant", content: chat.side_context.quote, run_status: "COMPLETED", run_id: null, created_at: 0 }]} /></blockquote>}
      <ConversationHistory messages={history.history?.messages ?? []} runs={history.history?.runs} liveMessages={running || sending || !history.history ? messages : undefined} isRunning={running || sending} />
      {history.activeRun && !running && <div className={styles.feedback}><p>侧聊运行尚未结束；请核对，不会重复发送。</p><Button size="sm" variant="ghost" onClick={() => void reconcileConversationRun(chat.session_id, history.activeRun!.run_id).then(history.refresh).catch((failure: unknown) => setFeedback(failure instanceof Error ? failure.message : "核对失败"))}>核对中断状态</Button></div>}
    </div>
    <div className={styles.composerArea}><form className={styles.composer} onSubmit={event => { event.preventDefault(); if (active) void stop(); else void send(); }}>
      <label className="sr-only" htmlFor="career-side-input">侧聊消息</label><textarea ref={input} id="career-side-input" placeholder="追问或处理旁支问题…" rows={1} maxLength={4000} value={state.draft} onChange={event => store.update(previous => ({ ...previous, draft: event.target.value }))} onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} />
      <AgentComposerTools readOnly={false} modelId={history.history?.session.model_id ?? chat.model_id} modelDisabled={active || history.loading || !!history.error} onModelChange={id => { const session = history.history?.session; if (session) void saveConversation(chat.session_id, session.version, { model_id: id }).then(history.refresh).catch((failure: unknown) => setFeedback(failure instanceof Error ? failure.message : "保存失败")); }}><TooltipIconButton type="submit" variant="default" className="size-8 rounded-full" disabled={stopping || history.loading || !!history.error || (!active && !state.draft.trim())} tooltip={active ? "停止侧聊运行" : "发送侧聊 · Ctrl/⌘ Enter"} aria-label={active ? "停止侧聊运行" : "发送侧聊"}>{active ? <Square className="size-3 fill-current" /> : <ArrowUp />}</TooltipIconButton></AgentComposerTools>
    </form>{feedback && <p role="status" className={styles.feedback}>{feedback}</p>}<p className={styles.sideSource}>收起、刷新保留；关闭丢弃。异常退出不保证即时停止，临时内容最多保留 24 小时后核对清理。</p>{!store.storageAvailable() && <p role="alert">当前浏览器无法保留侧聊视图，请勿刷新。</p>}</div>
    <Dialog open={confirmClose || !!replacement} onOpenChange={open => { if (!open && !closing) { setConfirmClose(false); clearReplacement(); } }}><DialogContent><DialogHeader><DialogTitle>{replacement ? "替换当前临时侧聊？" : active ? "先停止侧聊运行？" : "关闭并丢弃侧聊？"}</DialogTitle><DialogDescription>{active ? "只停止侧聊；核对服务端终态后才能丢弃。主任务和已保存成果不变。" : "侧聊文本和草稿不能找回。已保存材料、候选规则和外部结果保留。"}</DialogDescription></DialogHeader>{!active && <label className="flex gap-2 text-sm"><input type="checkbox" checked={suppress} onChange={event => setSuppress(event.target.checked)} />以后关闭不再提醒（运行中仍需确认）</label>}<div className="flex justify-end gap-2"><Button variant="outline" disabled={closing} onClick={() => { setConfirmClose(false); clearReplacement(); }}>保留侧聊</Button><Button disabled={closing || stopping} onClick={() => void discard()}>{active ? "请求停止，保留至终态" : "关闭并丢弃"}</Button></div></DialogContent></Dialog>
  </>;
}

"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useAuiState } from "@assistant-ui/react";
import { LoaderCircle } from "lucide-react";

import { AgentAction } from "@/components/workspace-actions";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Textarea } from "@/components/ui/textarea";
import { useDraftGuard } from "@/components/workspace-projects";
import {
  confirmMemory, createMemory, readMemories, readMemory, retireMemory, updateMemory,
  MemoryRequestError, type MemoryKind, type WorkspaceMemory,
} from "@/lib/memories";

const inputClass = "h-10 w-full rounded-md border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

function stateLabel(memory: WorkspaceMemory) {
  if (memory.state === "retired") return "已撤销";
  return memory.kind === "note" ? "笔记 · 待核实" : memory.state === "confirmed" ? "规则 · 已确认" : "规则 · 待确认";
}

export function WorkspaceMemories({ onDirtyChange }: { onDirtyChange?: (dirty: boolean) => void }) {
  const agentRunning = useAuiState(state => state.thread.isRunning);
  const [kind, setKind] = useState<MemoryKind>();
  const [includeRetired, setIncludeRetired] = useState(false);
  const [memories, setMemories] = useState<WorkspaceMemory[]>([]);
  const [cursor, setCursor] = useState<string>();
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [draftId, setDraftId] = useState<string | null>(null);
  const [draftKind, setDraftKind] = useState<MemoryKind>("note");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [editing, setEditing] = useState<WorkspaceMemory | null>(null);
  const [latest, setLatest] = useState<WorkspaceMemory | null>(null);
  const [needsCheck, setNeedsCheck] = useState(false);
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [cancelRequested, setCancelRequested] = useState(false);
  const dirty = Boolean((draftId && (title || content)) || (editing && (title !== editing.title || content !== editing.content)));
  useDraftGuard(dirty || Boolean(busyId));

  useEffect(() => {
    onDirtyChange?.(dirty || Boolean(busyId));
    return () => onDirtyChange?.(false);
  }, [dirty, busyId, onDirtyChange]);

  useEffect(() => {
    if (agentRunning) return;
    const controller = new AbortController();
    readMemories({ kind, includeRetired, cursor }, AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]))
      .then(page => {
        if (controller.signal.aborted) return;
        setMemories(current => cursor ? [...current, ...page.items.filter(item => !current.some(existing => existing.id === item.id))] : page.items);
        setNextCursor(page.next_cursor);
        setLoadError("");
      })
      .catch((failure: unknown) => {
        if (!controller.signal.aborted) setLoadError(failure instanceof Error ? failure.message : "暂时无法读取规则与笔记。");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [kind, includeRetired, cursor, attempt, agentRunning]);

  function reload() {
    setCursor(undefined); setLoading(true); setLoadError(""); setAttempt(value => value + 1);
  }

  function closeEditor() {
    setCancelRequested(false);
    setDraftId(null); setEditing(null); setLatest(null); setNeedsCheck(false);
    setTitle(""); setContent(""); setError("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (busyId || needsCheck || !title.trim() || !content.trim() || (!draftId && !editing)) return;
    setBusyId(editing?.id ?? "new"); setError(""); setNotice("");
    try {
      const saved = editing
        ? await updateMemory(editing, { title: title.trim(), content: content.trim() }, AbortSignal.timeout(20_000))
        : await createMemory({ id: draftId!, kind: draftKind, title: title.trim(), content: content.trim() }, AbortSignal.timeout(20_000));
      closeEditor();
      setNotice(saved.kind === "rule" ? "已保存为待确认规则。确认后可供伙伴读取；确认前不会影响后续工作。" : "笔记已保存，不会自动成为规则。");
      reload();
    } catch (failure: unknown) {
      setError(failure instanceof Error ? failure.message : "未能确认保存结果，请读取核对。");
      if (editing && failure instanceof MemoryRequestError && (failure.status === 0 || failure.status === 409 || failure.status >= 500)) setNeedsCheck(true);
    } finally { setBusyId(""); }
  }

  async function checkLatest() {
    if (!editing || busyId) return;
    setBusyId(editing.id);
    try {
      setLatest(await readMemory(editing.id, AbortSignal.timeout(20_000)));
      setError("");
    } catch (failure: unknown) { setError(failure instanceof Error ? failure.message : "暂时无法核对最新记录。"); }
    finally { setBusyId(""); }
  }

  async function transition(memory: WorkspaceMemory, action: "confirm" | "retire") {
    if (busyId) return;
    setBusyId(memory.id); setError(""); setNotice("");
    try {
      const saved = action === "confirm" ? await confirmMemory(memory, AbortSignal.timeout(20_000)) : await retireMemory(memory, AbortSignal.timeout(20_000));
      setMemories(current => current.flatMap(item => item.id !== saved.id ? [item] : saved.state === "retired" && !includeRetired ? [] : [saved]));
      setNotice(action === "confirm" ? "规则已确认；后续伙伴工作会按当前版本读取。" : "记录已撤销，查看撤销记录可以核对正文。");
    } catch (failure: unknown) { setError(failure instanceof Error ? failure.message : "操作结果尚未确认，请重新读取核对。"); }
    finally { setBusyId(""); }
  }

  const editorOpen = Boolean(draftId || editing);
  return <section className="mt-5 space-y-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="text-sm font-medium">长期上下文</h2><p className="mt-2 max-w-2xl text-xs leading-5 text-muted-foreground">保存有来源的经验，核对、纠正或撤销它。笔记不自动成为规则；已确认规则会在后续伙伴工作中按版本读取。</p></div>
      <div className="flex flex-wrap gap-2">
        <AgentAction prompt="我想沉淀一条职业经验。请和我澄清内容、来源和适用范围，再提出一条待我确认的笔记或规则。不要把提议说成已经生效。">和伙伴整理</AgentAction>
        <Button variant="outline" size="sm" disabled={editorOpen || Boolean(busyId)} onClick={() => { setDraftId(crypto.randomUUID()); setTitle(""); setContent(""); setError(""); }}>记录一条</Button>
      </div>
    </div>
    <div className="flex flex-wrap items-center justify-between gap-2">
      <div role="group" aria-label="上下文视图" className="flex flex-wrap gap-1">
        {([undefined, "rule", "note"] as const).map(option => <Button key={option ?? "all"} size="sm" variant={kind === option ? "secondary" : "ghost"} aria-pressed={kind === option} disabled={editorOpen || Boolean(busyId)} onClick={() => { setKind(option); setMemories([]); setNextCursor(null); reload(); }}>{option === "rule" ? "规则" : option === "note" ? "笔记" : "全部"}</Button>)}
      </div>
      <Button size="sm" variant="ghost" aria-pressed={includeRetired} disabled={editorOpen || Boolean(busyId)} onClick={() => { setIncludeRetired(value => !value); setMemories([]); setNextCursor(null); reload(); }}>{includeRetired ? "隐藏撤销记录" : "查看撤销记录"}</Button>
    </div>
    {editorOpen && <form onSubmit={save} className="space-y-4 rounded-xl border p-5">
      <div><h3 className="text-sm font-medium">{editing ? "纠正长期上下文" : "把一次经验留给下一次工作"}</h3><p className="mt-1 text-xs leading-5 text-muted-foreground">{editing?.kind === "rule" ? "保存将更新当前正文和版本，并把规则退回待确认。旧正文暂不保留为历史版本。" : "这条记录保存在服务端；请勿提供证件号、密码或验证码。"}</p></div>
      {!editing && <div role="group" aria-label="记录类型" className="flex gap-1">{(["note", "rule"] as const).map(option => <Button key={option} type="button" size="sm" variant={draftKind === option ? "secondary" : "ghost"} aria-pressed={draftKind === option} disabled={Boolean(busyId)} onClick={() => setDraftKind(option)}>{option === "rule" ? "规则" : "笔记"}</Button>)}</div>}
      <label className="block space-y-2 text-sm"><span>标题</span><input autoFocus aria-label={editing ? "纠正标题" : "记录标题"} value={title} onChange={event => setTitle(event.target.value)} maxLength={200} disabled={Boolean(busyId)} className={inputClass} /></label>
      <label className="block space-y-2 text-sm"><span>内容</span><Textarea aria-label={editing ? "纠正内容" : "记录内容"} value={content} onChange={event => setContent(event.target.value)} maxLength={8000} rows={4} disabled={Boolean(busyId)} /></label>
      {needsCheck && <div className="space-y-3 rounded-lg bg-muted/40 p-4 text-xs"><p>当前输入仍保留。先核对服务端记录，再决定是否继续纠正。</p><Button type="button" size="sm" variant="outline" disabled={Boolean(busyId)} onClick={checkLatest}>核对最新记录</Button>{latest && <><p className="font-medium">{latest.title} · {stateLabel(latest)}</p><p className="whitespace-pre-wrap break-words leading-6">{latest.content}</p>{latest.state !== "retired" && <Button type="button" size="sm" variant="outline" onClick={() => { setEditing(latest); setLatest(null); setNeedsCheck(false); }}>以最新版本继续纠正</Button>}</>}</div>}
      <div className="flex flex-wrap justify-end gap-2"><Button type="button" variant="ghost" disabled={Boolean(busyId)} onClick={() => { if (dirty) setCancelRequested(true); else closeEditor(); }}>取消</Button><Button type="submit" disabled={Boolean(busyId) || needsCheck || !title.trim() || !content.trim()}>{busyId && <LoaderCircle className="size-4 animate-spin" />}{editing ? "保存纠正" : draftKind === "rule" ? "保存为待确认" : "保存笔记"}</Button></div>
    </form>}
    {error && <div role="alert" className="space-y-3 rounded-lg border border-destructive/30 p-4 text-xs"><p>{error}</p><Button size="sm" variant="outline" disabled={Boolean(busyId)} onClick={reload}>重新读取</Button></div>}
    {notice && <p role="status" className="text-xs leading-5 text-muted-foreground">{notice}</p>}
    {loadError && <div role="alert" className="space-y-3 rounded-lg border border-destructive/30 p-4 text-xs"><p>{loadError}</p><Button size="sm" variant="outline" onClick={reload}>重试读取</Button></div>}
    {memories.length > 0 && <div className="divide-y rounded-xl border">{memories.map(memory => <article key={memory.id} className="space-y-3 p-5">
      <div className="flex flex-wrap items-start justify-between gap-3"><div><p className="text-xs text-muted-foreground">{stateLabel(memory)}</p><h3 className="mt-1 break-words text-sm font-medium">{memory.title}</h3></div><span className="text-xs text-muted-foreground">{new Date(memory.updated_at).toLocaleDateString("zh-CN")}</span></div>
      <p className="whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">{memory.content}</p>
      <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-3 text-xs"><span className="break-words text-muted-foreground">来源：{memory.source}</span>{memory.state !== "retired" && <div className="flex flex-wrap gap-2"><Button size="sm" variant="ghost" disabled={editorOpen || Boolean(busyId)} onClick={() => { setEditing(memory); setTitle(memory.title); setContent(memory.content); setError(""); setNotice(""); }}>纠正</Button>{memory.kind === "rule" && memory.state === "candidate" && <Button size="sm" variant="outline" disabled={editorOpen || Boolean(busyId)} onClick={() => transition(memory, "confirm")}>确认规则</Button>}<Button size="sm" variant="ghost" disabled={editorOpen || Boolean(busyId)} onClick={() => transition(memory, "retire")}>撤销</Button></div>}</div>
    </article>)}</div>}
    {loading ? <p role="status" className="flex items-center gap-2 py-6 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />正在读取长期上下文…</p> : !loadError && memories.length === 0 && <div className="rounded-xl border px-5 py-12 text-center"><h3 className="text-sm font-medium">还没有保存的规则或笔记</h3><p className="mt-2 text-xs text-muted-foreground">从一次真实工作后的观察开始，先记录，再决定是否确认规则。</p></div>}
    {!loading && !loadError && nextCursor && <Button variant="outline" disabled={editorOpen || Boolean(busyId)} onClick={() => { setLoading(true); setCursor(nextCursor); }}>加载更多记录</Button>}
    <Dialog open={cancelRequested} onOpenChange={setCancelRequested}><DialogContent><DialogHeader><DialogTitle>放弃未保存的输入？</DialogTitle><DialogDescription>已保存的记录保留；本次输入还未保存，放弃后不会恢复。</DialogDescription></DialogHeader><DialogFooter><Button variant="outline" onClick={() => setCancelRequested(false)}>继续编辑</Button><Button onClick={closeEditor}>放弃输入</Button></DialogFooter></DialogContent></Dialog>
  </section>;
}

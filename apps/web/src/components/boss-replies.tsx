"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { createLatestRequest } from "@/lib/latest-request";
import { BossReplySend } from "@/components/boss-reply-send";

type Reply = {
  id: string; conversation_id: string; message_id: string; version: string;
  status: "accepted" | "running" | "waiting" | "completed" | "failed" | "timed_out" | "cancelled";
  outcome: string | null; created_at: string;
  decision: { category: string; text: string; reason: string; facts: { field: string; quote: string }[] } | null;
};
export type ReplySource = { readTaskId: string; conversationId: string; messageId: string; content: string };
const labels = { accepted: "已受理，等待 Worker", running: "Agent 正在判断", waiting: "待处理", completed: "无需回复", failed: "判断失败", timed_out: "任务已超时", cancelled: "已停止" };
const categories: Record<string, string> = { routine: "回复草稿", acknowledgement: "询问岗位信息", resume_request: "请求简历", commitment: "需要确认安排", technical: "需要你回答", unknown: "依据不足", no_action: "无需回复" };

export function BossReplies({ connectionId, source, blocked, latestReadTaskId }: { connectionId: string; source: ReplySource | null; blocked: boolean; latestReadTaskId?: string | null }) {
  const [items, setItems] = useState<Reply[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [disclosure, setDisclosure] = useState<ReplySource | null>(null);
  const reads = useRef(createLatestRequest());
  const write = useRef<AbortController | null>(null);
  const base = "/api/recruiting/replies";
  const refresh = useCallback(async (before?: string) => {
    const controller = reads.current.start();
    try {
      const query = new URLSearchParams({ connection_id: connectionId });
      if (before) query.set("cursor", before);
      const response = await fetch(`${base}?${query}`, { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]) });
      if (!response.ok) throw new Error("Reply status unavailable");
      const page = await response.json() as { items: Reply[]; next_cursor: string | null };
      if (!reads.current.isCurrent(controller)) return;
      setItems(current => before ? [...current, ...page.items.filter(item => !current.some(old => old.id === item.id))] : page.items);
      setCursor(page.next_cursor);
    } catch (failure) {
      if (!reads.current.isCurrent(controller)) return;
      if (!(failure instanceof Error)) throw failure;
      setError("暂时无法读取回复任务，请核对状态。");
    }
  }, [connectionId]);
  useEffect(() => {
    const requests = reads.current;
    void refresh();
    return () => { requests.cancel(); write.current?.abort(); };
  }, [refresh]);
  const running = items.some(item => item.status === "accepted" || item.status === "running");
  useEffect(() => {
    if (!running) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { await refresh(); if (!stopped) timer = setTimeout(() => void poll(), 2000); };
    timer = setTimeout(() => void poll(), 2000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [running, refresh]);

  const mutate = async (path: string, method: "POST" | "DELETE", body: object, key?: string) => {
    if (write.current) return;
    const controller = new AbortController();
    write.current = controller;
    setPending(true); setError(null); setDisclosure(null);
    try {
      const response = await fetch(path, {
        method, headers: { "Content-Type": "application/json", ...(key ? { "Idempotency-Key": key } : {}) },
        body: JSON.stringify(body), signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]),
      });
      if (!response.ok) {
        const payload = await response.json() as { error?: { message?: string } };
        throw new Error(payload.error?.message ?? "未能确认回复任务，请核对状态。");
      }
      const saved = await response.json() as Reply;
      if (controller.signal.aborted) return;
      reads.current.cancel();
      setItems(current => [saved, ...current.filter(item => item.id !== saved.id)]);
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (!(failure instanceof Error)) throw failure;
      setError(failure.message);
    } finally {
      if (write.current === controller) write.current = null;
      if (!controller.signal.aborted) { setPending(false); await refresh(); }
    }
  };
  const existing = source && items.some(item => item.conversation_id === source.conversationId && item.message_id === source.messageId && !["failed", "timed_out", "cancelled"].includes(item.status));
  return <section aria-label="Agent 回复任务" className="mt-4 border-t pt-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h3 className="text-sm font-medium">Agent 回复</h3>
      <div className="flex gap-2">
        {source && <Button disabled={blocked || pending || !!existing} variant="outline" onClick={() => setDisclosure(source)}>生成回复建议</Button>}
        <Button variant="ghost" disabled={pending} onClick={() => { setError(null); void refresh(); }}>核对回复任务</Button>
      </div>
    </div>
    {items.length === 0 && <p className="mt-2 text-xs text-muted-foreground">读取会话详情后，Agent 可结合已确认的职业背景和规则判断最新来信。</p>}
    {error && <p role="alert" className="mt-2 text-sm text-destructive">{error}</p>}
    {items.map(item => <article key={item.id} className="mt-3 rounded-lg border p-3 text-sm">
      <p role="status">{labels[item.status]}{item.decision ? ` · ${categories[item.decision.category] ?? "待核对"}` : ""}</p>
      <p className="mt-1 text-xs text-muted-foreground">{new Date(item.created_at).toLocaleString()} · 会话 {item.conversation_id}</p>
      {item.decision && <><p className="mt-2">{item.decision.reason}</p>{item.decision.text && <p className="mt-2 whitespace-pre-wrap rounded-md bg-muted p-3">{item.decision.text}</p>}
        {item.decision.facts.length > 0 && <details className="mt-2 text-xs"><summary>已确认的事实依据</summary>{item.decision.facts.map((fact, index) => <p key={index} className="mt-1">{fact.field}：{fact.quote}</p>)}</details>}</>}
      {item.status === "waiting" && item.decision?.text && <p className="mt-2 text-xs text-muted-foreground">回复内容已保存，执行结果见下方。</p>}
      {item.status === "waiting" && item.decision && ["routine", "acknowledgement"].includes(item.decision.category) && <BossReplySend reply={{ ...item, decision: item.decision }} latestReadTaskId={latestReadTaskId} blocked={blocked || pending} />}
      <div className="mt-2 flex gap-2">
        {item.status === "accepted" && <Button disabled={pending} variant="outline" onClick={() => void mutate(`${base}/${item.id}/resume`, "POST", {})}>恢复任务派发</Button>}
        {["accepted", "running"].includes(item.status) && <Button disabled={pending} variant="ghost" onClick={() => void mutate(`${base}/${item.id}`, "DELETE", { version: item.version })}>停止此任务</Button>}
      </div>
    </article>)}
    {cursor && !running && <Button variant="ghost" onClick={() => void refresh(cursor)}>更早的回复任务</Button>}
    <Dialog open={!!disclosure} onOpenChange={open => { if (!open) setDisclosure(null); }}>
      <DialogContent><DialogTitle>让 Agent 判断这条来信</DialogTitle>
        <DialogDescription>本次会把该会话当前已加载的消息、已确认的职业背景和个人规则交给已配置模型，用于判断回复内容和需要你确认的事项。</DialogDescription>
        <p className="max-h-40 overflow-auto whitespace-pre-wrap text-sm">{disclosure?.content}</p>
        <DialogFooter><Button variant="outline" onClick={() => setDisclosure(null)}>取消</Button><Button disabled={pending || blocked} onClick={() => {
          if (!disclosure) return;
          void mutate(base, "POST", { connection_id: connectionId, read_task_id: disclosure.readTaskId, conversation_id: disclosure.conversationId, message_id: disclosure.messageId, disclose_to_model: true }, crypto.randomUUID());
        }}>生成并保存建议</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  </section>;
}

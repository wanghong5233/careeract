"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { createLatestRequest } from "@/lib/latest-request";

export type SendableReply = {
  id: string; version: string; conversation_id: string; message_id: string;
  decision: { text: string };
};
type Send = {
  id: string; text: string; conversation_id: string; message_id: string;
  status: "accepted" | "running" | "completed" | "unknown" | "failed" | "cancelled" | "timed_out" | "waiting";
  evidence_message_id: string | null;
  cleanup_required: boolean;
};
const labels = { accepted: "已授权，等待执行", running: "正在发送并核验", completed: "已核验发送", unknown: "发送结果未知，请人工核对", failed: "未完成发送", cancelled: "已取消", timed_out: "已超时", waiting: "等待处理" };

export function BossReplySend({ reply, blocked, latestReadTaskId }: { reply: SendableReply; blocked: boolean; latestReadTaskId?: string | null }) {
  const [action, setAction] = useState<Send | null>(null);
  const [review, setReview] = useState<SendableReply | null>(null);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const reads = useRef(createLatestRequest());
  const write = useRef<AbortController | null>(null);
  const base = `/api/recruiting/replies/${reply.id}/send`;
  const refresh = useCallback(async () => {
    const controller = reads.current.start();
    try {
      const response = await fetch(base, { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]) });
      if (!response.ok) throw new Error("发送状态暂不可用");
      const saved = await response.json() as Send | null;
      if (reads.current.isCurrent(controller)) { setAction(saved); setLoaded(true); }
    } catch (failure) {
      if (!reads.current.isCurrent(controller)) return;
      if (!(failure instanceof Error)) throw failure;
      setError("无法核对发送状态，请稍后读取；不要重复授权。");
    }
  }, [base]);
  useEffect(() => {
    const requests = reads.current;
    void refresh();
    return () => { requests.cancel(); write.current?.abort(); };
  }, [refresh]);
  const running = action?.status === "accepted" || action?.status === "running";
  useEffect(() => {
    if (!running) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { await refresh(); if (!stopped) timer = setTimeout(() => void poll(), 2000); };
    timer = setTimeout(() => void poll(), 2000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [running, refresh]);
  const authorize = async () => {
    if (!review || write.current) return;
    const captured = review;
    const controller = new AbortController();
    write.current = controller;
    setPending(true); setLoaded(false); setReview(null); setError(null);
    try {
      const response = await fetch(base, {
        method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": crypto.randomUUID() },
        body: JSON.stringify({ version: captured.version, authorize_send: true }),
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]),
      });
      if (!response.ok) {
        const payload = await response.json() as { error?: { message?: string } };
        throw new Error(payload.error?.message ?? "无法确认发送任务，请读取状态。");
      }
      const saved = await response.json() as Send;
      if (!controller.signal.aborted) { reads.current.cancel(); setAction(saved); }
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (!(failure instanceof Error)) throw failure;
      setError(failure.message);
    } finally {
      if (write.current === controller) write.current = null;
      if (!controller.signal.aborted) { setPending(false); await refresh(); }
    }
  };
  const control = async (method: "POST" | "DELETE", reconcile = false) => {
    if (write.current) return;
    const controller = new AbortController();
    write.current = controller; setPending(true); setError(null);
    try {
      const response = await fetch(reconcile ? `${base}/reconcile` : method === "POST" ? `${base}/resume` : base, {
        method, headers: { "Content-Type": "application/json" }, body: reconcile ? JSON.stringify({ read_task_id: latestReadTaskId }) : "{}",
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(30_000)]),
      });
      if (!response.ok) throw new Error("任务状态已变化，请核对结果。");
      if (!controller.signal.aborted) setAction(await response.json() as Send);
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (!(failure instanceof Error)) throw failure;
      setError(failure.message);
    } finally {
      if (write.current === controller) write.current = null;
      if (!controller.signal.aborted) { setPending(false); await refresh(); }
    }
  };
  return <div className="mt-3" aria-label="回复发送">
    {action && <p role="status" className="text-xs">{labels[action.status]}{action.evidence_message_id ? ` · 消息 ${action.evidence_message_id}` : ""}</p>}
    {error && <p role="alert" className="mt-2 text-xs text-destructive">{error}</p>}
    {action?.cleanup_required && <p role="status" className="mt-2 text-xs">发送证据已保留，浏览器正在核对释放。</p>}
    <div className="mt-2 flex gap-2">
      {!action && <Button variant="outline" disabled={blocked || pending || !loaded} onClick={() => setReview(reply)}>审阅并发送回复</Button>}
      {action?.status === "accepted" && <><Button variant="outline" disabled={pending || blocked} onClick={() => void control("POST")}>恢复发送任务派发</Button><Button variant="ghost" disabled={pending} onClick={() => void control("DELETE")}>撤销未开始的发送</Button></>}
      {action?.status === "unknown" && !action.cleanup_required && <Button variant="outline" disabled={pending || blocked || !latestReadTaskId} onClick={() => void control("POST", true)}>使用最新会话读取核验发送</Button>}
      <Button variant="ghost" disabled={pending} onClick={() => { setError(null); void refresh(); }}>核对发送结果</Button>
    </div>
    <Dialog open={!!review} onOpenChange={open => { if (!open) setReview(null); }}>
      <DialogContent><DialogTitle>发送这条 BOSS 回复</DialogTitle>
        <DialogDescription>本次只授权向下列会话发送这份已保存回复。执行前会重新核验最新来信，确认没有人工草稿；结果未知时停止，不自动重发。</DialogDescription>
        <p className="text-xs text-muted-foreground">会话 {review?.conversation_id} · 来信 {review?.message_id}</p>
        <p className="max-h-60 overflow-auto whitespace-pre-wrap rounded-md bg-muted p-3 text-sm">{review?.decision.text}</p>
        <DialogFooter><Button variant="outline" onClick={() => setReview(null)}>取消</Button><Button disabled={blocked || pending} onClick={() => void authorize()}>授权本次发送</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  </div>;
}

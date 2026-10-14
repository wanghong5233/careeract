"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { createLatestRequest } from "@/lib/latest-request";

type Conversation = { conversation_id: string; recruiter_name: string | null; company: string | null };
type Automation = {
  id: string; version: string;
  status: "accepted" | "running" | "waiting" | "completed" | "cancelled" | "timed_out";
  conversation_ids: string[]; expires_at: string; max_sends: number; sends_reserved: number;
  outcome: string | null;
};
const labels = { accepted: "已受理，等待执行", running: "自动回复运行中", waiting: "等待处理", completed: "已完成", cancelled: "已停止", timed_out: "已到期" };
const outcomes: Record<string, string> = {
  resume_request: "招聘方请求简历，简历发送尚待接入。", commitment: "涉及面试、时间或其他承诺，需要你处理。",
  technical: "技术考核需要你处理。", unknown: "缺少已确认事实或回复依据，需要你处理。",
  judgment_requires_review: "回复判断未完成，请查看回复建议。", read_requires_review: "会话读取未通过，请查看读取任务。",
  scope_or_control_changed: "会话范围或控制权变化，已停止自动发送。", send_requires_review: "发送结果或浏览器释放未确认，请核对发送记录。",
  service_requires_review: "服务未完成本次操作，请核对任务。", connection_changed: "平台连接已变化。",
  interrupted_step_requires_review: "执行中断，保留原记录，请核对任务；不会重复发送。", limit_reached: "已达到本次发送上限。",
  expired: "本次委托已到期。", stopped: "后续发送已撤销；已经开始的操作仍需核对结果。",
};

export function BossAutomation({ connectionId, version, conversations, blocked, onActiveChange }: {
  connectionId: string; version: string; conversations: Conversation[]; blocked: boolean;
  onActiveChange: (active: boolean) => void;
}) {
  const [task, setTask] = useState<Automation | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [review, setReview] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [duration, setDuration] = useState(60);
  const [limit, setLimit] = useState(5);
  const reads = useRef(createLatestRequest());
  const write = useRef<AbortController | null>(null);
  const key = useRef<string | null>(null);
  const base = "/api/recruiting/automations";
  const active = task?.status === "accepted" || task?.status === "running" || task?.status === "waiting";
  const refresh = useCallback(async () => {
    const controller = reads.current.start();
    try {
      const response = await fetch(`${base}?connection_id=${encodeURIComponent(connectionId)}`, {
        cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]),
      });
      if (!response.ok) throw new Error("无法读取自动回复状态，请稍后核对。");
      const saved = await response.json() as Automation | null;
      if (reads.current.isCurrent(controller)) { setTask(saved); setLoaded(true); }
    } catch (failure) {
      if (!reads.current.isCurrent(controller)) return;
      if (!(failure instanceof Error)) throw failure;
      setLoaded(false); setError(failure.message);
    }
  }, [connectionId]);
  useEffect(() => {
    const requests = reads.current;
    void refresh();
    return () => { requests.cancel(); write.current?.abort(); };
  }, [refresh]);
  useEffect(() => { onActiveChange(active || !loaded || pending); }, [active, loaded, pending, onActiveChange]);
  useEffect(() => {
    if (!active) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => { await refresh(); if (!stopped) timer = setTimeout(() => void poll(), 3000); };
    timer = setTimeout(() => void poll(), 3000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [active, refresh]);
  const mutate = async (action: "start" | "stop" | "dispatch") => {
    if (write.current || (action === "start" && (blocked || active || !loaded || !selected.length))) return;
    if (action !== "start" && !task) return;
    const controller = new AbortController();
    write.current = controller; reads.current.cancel(); setPending(true); setError(null); setReview(false);
    const body = action === "start" ? {
      connection_id: connectionId, version, conversation_ids: selected, max_sends: limit,
      duration_minutes: duration, interval_seconds: 300, authorize_replies: true, disclose_to_model: true,
    } : action === "stop" ? { version: task!.version } : {};
    if (action === "start") key.current ??= crypto.randomUUID();
    try {
      const response = await fetch(action === "start" ? base : `${base}/${task!.id}${action === "dispatch" ? "/dispatch" : ""}`, {
        method: action === "stop" ? "DELETE" : "POST",
        headers: { "Content-Type": "application/json", ...(action === "start" ? { "Idempotency-Key": key.current! } : {}) },
        body: JSON.stringify(body), signal: AbortSignal.any([controller.signal, AbortSignal.timeout(65_000)]),
      });
      if (!response.ok) throw new Error("操作结果未确认，请核对任务状态；不会自动重复授权。");
      const saved = await response.json() as Automation;
      if (!controller.signal.aborted) { reads.current.cancel(); setTask(saved); key.current = null; }
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (!(failure instanceof Error)) throw failure;
      setError(failure.message);
    } finally {
      if (write.current === controller) write.current = null;
      if (!controller.signal.aborted) { setPending(false); await refresh(); }
    }
  };
  const openReview = () => { key.current = null; setSelected([]); setReview(true); };
  return <section className="mt-4 rounded-lg border p-3" aria-label="自动回复委托">
    <p className="text-sm font-medium">自动回复</p>
    <p className="mt-1 text-xs text-muted-foreground">对选定会话每 5 分钟检查新来信，依据已确认职业背景回复常规问题。关闭页面后继续运行。</p>
    {task && <div className="mt-2 text-xs" role="status"><p>{labels[task.status]} · 已受理发送 {task.sends_reserved}/{task.max_sends} 次 · 截止 {new Date(task.expires_at).toLocaleString()}</p>{task.outcome && <p className="mt-1">{outcomes[task.outcome] ?? "请核对关联任务。"}</p>}</div>}
    {error && <p className="mt-2 text-xs text-destructive" role="alert">{error}</p>}
    <div className="mt-2 flex flex-wrap gap-2">
      {!active && <Button variant="outline" disabled={blocked || pending || !loaded || !conversations.length} onClick={openReview}>设置自动回复</Button>}
      {active && <Button variant="outline" disabled={pending} onClick={() => void mutate("stop")}>停止自动回复</Button>}
      {task?.status === "accepted" && <Button variant="outline" disabled={pending} onClick={() => void mutate("dispatch")}>恢复任务派发</Button>}
      <Button variant="ghost" disabled={pending} onClick={() => { setError(null); void refresh(); }}>核对自动回复状态</Button>
    </div>
    <Dialog open={review} onOpenChange={setReview}><DialogContent><DialogTitle>设置自动回复委托</DialogTitle>
      <DialogDescription>选择已读取的会话。本次允许向这些招聘方自动发送有事实依据的常规回复，并将相关消息及已确认职业背景提供给模型判断。简历请求、技术考核和承诺转为待处理，不自动发送简历或打招呼。发送结果未知时停止。</DialogDescription>
      <div className="max-h-48 overflow-auto">{conversations.map(item => <label key={item.conversation_id} className="flex items-center gap-2 py-1 text-sm"><input type="checkbox" checked={selected.includes(item.conversation_id)} disabled={!selected.includes(item.conversation_id) && selected.length >= 20} onChange={event => setSelected(current => event.target.checked ? [...current, item.conversation_id] : current.filter(id => id !== item.conversation_id))} />{item.recruiter_name ?? "招聘方"} · {item.company ?? item.conversation_id}</label>)}</div>
      <label className="text-sm">持续时间<select className="ml-2 rounded border p-1" value={duration} onChange={event => setDuration(Number(event.target.value))}><option value={30}>30 分钟</option><option value={60}>1 小时</option><option value={240}>4 小时</option><option value={480}>8 小时</option></select></label>
      <label className="text-sm">最多发送<select className="ml-2 rounded border p-1" value={limit} onChange={event => setLimit(Number(event.target.value))}>{[1, 5, 10, 20].map(value => <option key={value} value={value}>{value} 次</option>)}</select></label>
      <p className="text-xs text-muted-foreground">随时可停止委托。已开始发送的操作会保留核验记录；次数表示已受理的发送尝试，成功以回复发送记录为准。</p>
      <DialogFooter><Button variant="outline" onClick={() => setReview(false)}>取消</Button><Button disabled={blocked || pending || !selected.length} onClick={() => void mutate("start")}>授权并启动自动回复</Button></DialogFooter>
    </DialogContent></Dialog>
  </section>;
}

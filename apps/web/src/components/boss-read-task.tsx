"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, RefreshCw } from "lucide-react";

import { BrowserScene } from "@/components/browser-scene";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogTitle } from "@/components/ui/dialog";
import { createLatestRequest } from "@/lib/latest-request";

type TaskStatus = "accepted" | "running" | "waiting" | "failed" | "timed_out" | "cancelled" | "completed" | "unknown";
type ReadTask = { task_id: string; task_status: TaskStatus; browser_session_id: string | null; outcome: string | null };
type ReadResult = {
  observed_at: string;
  page: {
    title: string; url: string; kind: string; state: "ready" | "needs_login" | "risk" | "unstable" | "unknown";
    jobs: { job_id: string; title: string; company: string }[];
    conversations: { conversation_id: string; recruiter_name: string | null; company: string | null; last_message: string | null }[];
    messages: { message_id: string; conversation_id: string | null; content: string; sender: string; sent_at: string | null; resume_attachment?: { filename: string; sent_by_candidate: boolean; request_message_id: string | null } | null }[];
    resume_control?: { conversation_id: string; state: "available" | "unavailable" | "unknown"; attachment_reported: boolean | null } | null;
  };
};

const labels: Record<TaskStatus, string> = {
  accepted: "已受理", running: "正在读取", waiting: "等待人工", failed: "读取失败",
  timed_out: "已超时", cancelled: "已取消", completed: "读取完成", unknown: "结果待核对",
};
const pageLabels = { ready: "已识别页面", needs_login: "需要重新登录", risk: "需要平台安全验证", unstable: "页面尚未稳定", unknown: "尚未识别页面结构" };

export function BossReadTask({ connectionId, version, blocked }: { connectionId: string; version: string; blocked: boolean }) {
  const [task, setTask] = useState<ReadTask | null>(null);
  const [result, setResult] = useState<ReadResult | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [selectedConversation, setSelectedConversation] = useState<{ id: string; name: string } | null>(null);
  const [executing, setExecuting] = useState(false);
  const [stopping, setStopping] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const reads = useRef(createLatestRequest());
  const writes = useRef<AbortController | null>(null);
  const stops = useRef<AbortController | null>(null);
  const requestKey = useRef<string | null>(null);
  const base = `/api/connections/boss/${connectionId}/read`;

  const refresh = useCallback(async () => {
    const controller = reads.current.start();
    try {
      const response = await fetch(base, { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]) });
      if (!response.ok) throw new Error("Read task unavailable");
      const current = await response.json() as ReadTask | null;
      if (!reads.current.isCurrent(controller)) return;
      setTask(current);
      if (current) {
        const observed = await fetch(`${base}/${current.task_id}/result`, { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]) });
        if (!observed.ok) throw new Error("Read result unavailable");
        const page = await observed.json() as ReadResult | null;
        if (!reads.current.isCurrent(controller)) return;
        setResult(page);
      } else {
        setResult(null);
      }
      setError(null);
      return current;
    } catch (failure) {
      if (!reads.current.isCurrent(controller)) return;
      if (!(failure instanceof Error)) throw failure;
      setError("暂时无法核对读取任务，请重新读取状态；不会重复执行。");
    } finally {
      if (reads.current.isCurrent(controller)) setLoading(false);
    }
  }, [base]);

  useEffect(() => {
    const requests = reads.current;
    void refresh();
    return () => { requests.cancel(); writes.current?.abort(); stops.current?.abort(); };
  }, [refresh]);

  useEffect(() => {
    if (!executing && task?.task_status !== "running" && task?.task_status !== "waiting") return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      await refresh();
      if (!stopped) timer = setTimeout(() => void poll(), 2000);
    };
    timer = setTimeout(() => void poll(), 2000);
    return () => { stopped = true; clearTimeout(timer); };
  }, [executing, task?.task_status, refresh]);

  const execute = async (accepted: ReadTask, controller: AbortController) => {
    const response = await fetch(`${base}/${accepted.task_id}/run`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(120_000)]),
    });
    if (!response.ok) throw new Error("Read execution unconfirmed");
  };

  const start = async (resume = false) => {
    if (writes.current || stops.current || blocked || loading || task?.task_status === "running" || task?.task_status === "waiting" || task?.task_status === "unknown") return;
    const controller = new AbortController();
    writes.current = controller;
    setConfirmOpen(false);
    setExecuting(true);
    setError(null);
    try {
      let accepted = task;
      if (!resume) {
        requestKey.current ??= crypto.randomUUID();
        const response = await fetch(base, {
          method: "POST", headers: { "Content-Type": "application/json", "Idempotency-Key": requestKey.current },
          body: JSON.stringify({ version, authorize_read: true, ...(selectedConversation ? { conversation_id: selectedConversation.id } : {}) }),
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]),
        });
        if (!response.ok) throw new Error("Read acceptance unconfirmed");
        accepted = await response.json() as ReadTask;
        if (controller.signal.aborted) return;
        reads.current.cancel();
        setTask(accepted);
        setResult(null);
        requestKey.current = null;
      }
      if (!accepted || accepted.task_status !== "accepted") throw new Error("Read task cannot start");
      await execute(accepted, controller);
      if (!controller.signal.aborted) await refresh();
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (!(failure instanceof Error)) throw failure;
      const current = await refresh();
      if (!controller.signal.aborted) setError(current?.task_status === "failed"
        ? "本次未完成有效业务读取，浏览器已释放。请查看页面状态后再发起读取。"
        : "执行结果未确认，请核对任务与页面结果；不会自动重试。");
    } finally {
      if (writes.current === controller) writes.current = null;
      if (!controller.signal.aborted) setExecuting(false);
    }
  };

  const active = executing || stopping || task?.task_status === "running" || task?.task_status === "waiting" || task?.task_status === "unknown";
  const stop = async () => {
    if (stops.current || !task || !["accepted", "running", "waiting"].includes(task.task_status)) return;
    const controller = new AbortController();
    stops.current = controller;
    setStopping(true);
    setError(null);
    try {
      const response = await fetch(`${base}/${task.task_id}`, {
        method: "DELETE", headers: { "Content-Type": "application/json" }, body: "{}",
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(75_000)]),
      });
      if (!response.ok) throw new Error("Read stop unconfirmed");
      const current = await response.json() as ReadTask;
      if (controller.signal.aborted) return;
      reads.current.cancel();
      setTask(current);
      await refresh();
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (!(failure instanceof Error)) throw failure;
      await refresh();
      if (!controller.signal.aborted) setError("停止结果尚未确认，请核对状态；不会重新执行读取。");
    } finally {
      if (stops.current === controller) stops.current = null;
      if (!controller.signal.aborted) setStopping(false);
    }
  };
  const reconcile = async () => {
    if (writes.current || stops.current || !task || task.task_status !== "unknown") return;
    const controller = new AbortController();
    writes.current = controller;
    setExecuting(true);
    try {
      const response = await fetch(`${base}/${task.task_id}/reconcile`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: "{}",
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]),
      });
      if (!response.ok) throw new Error("Release not confirmed");
      if (!controller.signal.aborted) await refresh();
    } catch (failure) {
      if (controller.signal.aborted) return;
      if (!(failure instanceof Error)) throw failure;
      setError("浏览器释放尚未确认，请稍后核对；本次读取不会重新执行。");
    } finally {
      if (writes.current === controller) writes.current = null;
      if (!controller.signal.aborted) setExecuting(false);
    }
  };
  return <section aria-label="BOSS 页面读取" className="mt-5 border-t pt-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h3 className="text-sm font-medium">页面读取</h3><p className="mt-1 text-xs text-muted-foreground">从保存登录恢复并打开沟通页，读取结果可在刷新后找回。不会发送消息或简历。</p></div>
      <div className="flex items-center gap-2">
        <Button disabled={blocked || active || loading} variant="outline" onClick={() => { if (task?.task_status === "accepted") void start(true); else { setSelectedConversation(null); setConfirmOpen(true); } }}>{executing && <LoaderCircle className="size-3.5 animate-spin" />}{task?.task_status === "accepted" ? "执行已受理读取" : "读取 BOSS 页面"}</Button>
        <Button variant="ghost" onClick={() => void refresh()}><RefreshCw className="size-3.5" />核对读取结果</Button>
        {task && ["accepted", "running", "waiting"].includes(task.task_status) && <Button disabled={stopping} variant="outline" onClick={() => void stop()}>{stopping ? "正在停止" : task.task_status === "waiting" ? "核对停止并释放" : "停止读取"}</Button>}
        {task?.task_status === "unknown" && <Button disabled={executing || stopping} variant="outline" onClick={() => void reconcile()}>核对释放并结束</Button>}
      </div>
    </div>
    {blocked && <p className="mt-2 text-xs text-muted-foreground">请先关闭上方观看现场，以释放本机浏览器会话。</p>}
    {task && <p role="status" className="mt-3 text-xs">{task.outcome === "read_stop_requested" ? "停止已请求 · 等待浏览器释放核验" : labels[task.task_status]}{executing && task.task_status === "accepted" ? " · 执行请求已发出" : ""}</p>}
    {(task?.task_status === "running" || task?.task_status === "waiting") && task.browser_session_id && <BrowserScene key={task.browser_session_id} sessionId={task.browser_session_id} />}
    {result && <div className="mt-3 rounded-lg border bg-background p-3 text-xs leading-5">
      <p>{result.page.kind === "conversations" && result.page.conversations.length > 0 && result.page.messages.length === 0 ? "已读取会话列表摘要 · 消息详情待核验" : pageLabels[result.page.state]} · {new Date(result.observed_at).toLocaleString()}</p>
      <p className="mt-1 font-medium">{result.page.title}</p><p className="break-all text-muted-foreground">{result.page.url}</p>
      {task?.task_status !== "completed" && <p className="mt-2 text-amber-700 dark:text-amber-300">{task?.task_status === "failed" ? "这是已保存的页面观察；本次未完成有效业务读取。" : "这是已保存的页面观察；本次任务尚未确认完成。"}</p>}
      {result.page.jobs.map(job => <p key={job.job_id} className="mt-2">{job.title} · {job.company}</p>)}
      {result.page.conversations.map(conversation => <div key={conversation.conversation_id} className="mt-2"><div className="flex items-center justify-between gap-2"><p>{conversation.recruiter_name ?? "招聘方"} · {conversation.company ?? ""}</p><Button variant="ghost" disabled={blocked || active || loading || task?.task_status === "accepted"} onClick={() => { setSelectedConversation({ id: conversation.conversation_id, name: conversation.recruiter_name ?? "招聘方" }); setConfirmOpen(true); }}>读取会话详情</Button></div><p className="text-muted-foreground">{conversation.last_message}</p>{result.page.messages.filter(message => message.conversation_id === conversation.conversation_id).map(message => <div key={message.message_id} className="mt-2 rounded border p-2"><p className="text-muted-foreground">{({ recruiter: "招聘方", candidate: "我", system: "平台提示" } as Record<string, string>)[message.sender] ?? "方向待核验"} · {message.sent_at ? new Date(message.sent_at).toLocaleString() : "时间待核验"}</p><p className="whitespace-pre-wrap">{message.content}</p></div>)}</div>)}
      {result.page.messages.length > 0 && <p className="mt-2 text-muted-foreground">已核验当前加载的消息与最新消息标识；不代表全部历史记录，尚未开放自动回复或简历发送。</p>}
      {result.page.messages.filter(message => message.resume_attachment).map(message => <p key={`resume-${message.message_id}`} className="mt-2 text-muted-foreground">历史简历卡片（{message.sender === "candidate" ? "我方消息" : message.sender === "recruiter" ? "招聘方消息" : "平台消息"}）：{message.resume_attachment!.filename}。这是当前加载的历史记录，不能证明发送成功、待发送材料的版本或再次发送许可。</p>)}
      {result.page.resume_control && <p className="mt-2 text-muted-foreground">简历入口：{({ available: "页面可用", unavailable: "页面当前不可用", unknown: "尚未核验" })[result.page.resume_control.state]}。材料身份与版本尚未确认，不能据此自动发送。</p>}
      {result.page.kind === "conversations" && result.page.conversations.length === 0 && result.page.messages.length === 0 && <p className="mt-2 text-muted-foreground">已识别沟通页，尚未提取到可核验的会话或消息。</p>}
    </div>}
    {error && <p role="alert" className="mt-3 text-xs text-destructive">{error}</p>}
    <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}><DialogContent><DialogTitle>{selectedConversation ? `读取 ${selectedConversation.name} 的会话？` : "允许读取 BOSS 页面？"}</DialogTitle><DialogDescription>{selectedConversation ? "本次会打开指定招聘方的会话，核验当前加载的消息并保存结果。打开会话可能标记已读。" : "本次将恢复已保存登录，打开 BOSS 沟通页并读取会话信息，保存读取结果。"}授权最长 15 分钟，不包含消息回复、简历发送或自动重试。</DialogDescription><DialogFooter><Button variant="outline" onClick={() => setConfirmOpen(false)}>取消</Button><Button onClick={() => void start()}>允许并读取</Button></DialogFooter></DialogContent></Dialog>
  </section>;
}

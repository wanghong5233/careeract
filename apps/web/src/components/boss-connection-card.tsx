"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { createLatestRequest } from "@/lib/latest-request";
import { cn } from "@/lib/utils";

type ConnectionStatus = "pending" | "waiting_for_login" | "waiting_for_verification" | "connected" | "blocked" | "revoked" | "failed";
type Connection = { id: string; version: string; status: ConnectionStatus };

const labels: Record<ConnectionStatus, string> = {
  pending: "连接请求已记录",
  waiting_for_login: "等待登录",
  waiting_for_verification: "等待安全验证",
  connected: "已连接",
  blocked: "需要人工处理",
  revoked: "请求已撤销",
  failed: "连接失败",
};

export function BossConnectionCard() {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [busy, setBusy] = useState<"read" | "start" | "revoke" | null>("read");
  const [error, setError] = useState<string | null>(null);
  const [needsReconciliation, setNeedsReconciliation] = useState(false);
  const requests = useRef(createLatestRequest());
  const requestKey = useRef<string | null>(null);
  const writing = useRef(false);

  const load = useCallback(async () => {
    if (writing.current) return;
    const controller = requests.current.start();
    setBusy("read");
    try {
      const response = await fetch("/api/connections/boss", { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]) });
      if (!response.ok) throw new Error("Connection unavailable");
      const current = await response.json() as Connection | null;
      if (!requests.current.isCurrent(controller)) return;
      setConnection(current);
      setNeedsReconciliation(false);
      setError(null);
    } catch (failure) {
      if (!requests.current.isCurrent(controller)) return;
      if (!(failure instanceof Error)) throw failure;
      setError("无法读取连接状态，请重新读取后再操作。");
      setNeedsReconciliation(true);
    } finally {
      if (requests.current.isCurrent(controller)) setBusy(null);
    }
  }, []);

  useEffect(() => {
    void load();
    const tracker = requests.current;
    return () => tracker.cancel();
  }, [load]);

  const change = async (action: "start" | "revoke") => {
    if (writing.current || busy || needsReconciliation || (action === "revoke" && !connection)) return;
    writing.current = true;
    const controller = requests.current.start();
    setBusy(action);
    setError(null);
    requestKey.current ??= crypto.randomUUID();
    try {
      const response = await fetch(action === "start" ? "/api/connections/boss" : `/api/connections/boss/${connection!.id}`, {
        method: action === "start" ? "POST" : "DELETE",
        headers: { "Content-Type": "application/json", ...(action === "start" ? { "Idempotency-Key": requestKey.current } : {}) },
        body: JSON.stringify(action === "start" ? {} : { version: connection!.version }),
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]),
      });
      if (!response.ok) throw new Error("Connection outcome unconfirmed");
      const current = await response.json() as Connection;
      if (!requests.current.isCurrent(controller)) return;
      setConnection(current);
      requestKey.current = null;
    } catch (failure) {
      if (!requests.current.isCurrent(controller)) return;
      if (!(failure instanceof Error)) throw failure;
      setNeedsReconciliation(true);
      setError("未能确认请求结果，请先重新读取连接状态；不会自动重试。");
    } finally {
      writing.current = false;
      if (requests.current.isCurrent(controller)) setBusy(null);
    }
  };

  const active = connection && !["revoked", "failed"].includes(connection.status);
  return <section aria-labelledby="boss-connection-title" className="mb-5 rounded-xl border bg-muted/20 p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id="boss-connection-title" className="text-sm font-medium">连接 BOSS 直聘</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">招聘沟通需要先在隔离浏览器中完成登录和安全验证。</p></div>
      <span role="status" className={cn("rounded-full px-2 py-1 text-[11px] font-medium", connection?.status === "connected" ? "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-200" : "bg-muted text-muted-foreground")}>
        {busy === "read" ? "读取连接状态" : needsReconciliation ? "状态待核对" : connection ? labels[connection.status] : "尚未连接"}
      </span>
    </div>
    <p className="mt-4 max-w-2xl text-xs leading-5 text-muted-foreground">密码、短信验证码和验证码只应由你在安全浏览器中输入，不会进入 Agent 对话或普通业务记录。</p>
    <p className="mt-2 max-w-2xl text-xs leading-5 text-muted-foreground">当前可记录和撤销连接请求，刷新后仍可找回。浏览器登录入口尚未开放，记录请求不会启动浏览器或发送消息。</p>
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <Button disabled={busy !== null || needsReconciliation || Boolean(active)} variant="outline" onClick={() => void change("start")}>
        {busy === "start" && <LoaderCircle className="size-3.5 animate-spin" />}{active ? "请求已记录" : "记录连接请求"}
      </Button>
      {active && <Button disabled={busy !== null || needsReconciliation} variant="ghost" onClick={() => void change("revoke")}>{busy === "revoke" && <LoaderCircle className="size-3.5 animate-spin" />}撤销连接请求</Button>}
      <Button disabled={busy !== null} variant="ghost" onClick={() => void load()}><RefreshCw className="size-3.5" />重新读取</Button>
    </div>
    {error && <p role="alert" className="mt-3 text-xs text-destructive">{error}</p>}
  </section>;
}

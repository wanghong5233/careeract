"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ExternalLink, LoaderCircle, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { createLatestRequest } from "@/lib/latest-request";
import { cn } from "@/lib/utils";

type ConnectionStatus = "pending" | "waiting_for_login" | "waiting_for_verification" | "connected" | "blocked" | "revoked" | "failed";
type Connection = { id: string; version: string; status: ConnectionStatus };
type LoginExecution = {
  attempt_status: "accepted" | "running" | "waiting" | "unknown" | "failed" | "cancelled" | "completed";
  authorization_status: "active" | "revoked" | "expired";
  outcome: string | null;
  browser_session_id: string | null;
};

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
  const [login, setLogin] = useState<LoginExecution | null>(null);
  const [loginAvailable, setLoginAvailable] = useState<boolean | null>(null);
  const [busy, setBusy] = useState<"read" | "start" | "stop" | null>("read");
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
      if (current?.id) {
        const loginResponse = await fetch(`/api/connections/boss/${current.id}/login`, { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]) });
        if (loginResponse.ok) {
          setLoginAvailable(true);
          setLogin(await loginResponse.json() as LoginExecution | null);
        } else if (loginResponse.status === 404) {
          setLoginAvailable(true);
          setLogin(null);
        } else if (loginResponse.status === 503) {
          setLoginAvailable(false);
          setLogin(null);
        } else {
          throw new Error("Login state unavailable");
        }
      } else {
        setLoginAvailable(null);
        setLogin(null);
      }
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

  const startLogin = async () => {
    if (writing.current || busy || needsReconciliation || loginAvailable === false) return;
    writing.current = true;
    const controller = requests.current.start();
    setBusy("start");
    setError(null);
    requestKey.current ??= crypto.randomUUID();
    try {
      let current = connection;
      if (!current || ["revoked", "failed"].includes(current.status)) {
        const response = await fetch("/api/connections/boss", {
          method: "POST",
          headers: { "Content-Type": "application/json", "Idempotency-Key": requestKey.current },
          body: "{}",
          signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]),
        });
        if (!response.ok) throw new Error("Connection outcome unconfirmed");
        current = await response.json() as Connection;
        setConnection(current);
      }
      const response = await fetch(`/api/connections/boss/${current.id}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "Idempotency-Key": requestKey.current },
        body: JSON.stringify({ version: current.version, authorize_login: true }),
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]),
      });
      if (!response.ok) throw new Error("Connection outcome unconfirmed");
      const execution = await response.json() as LoginExecution;
      if (!requests.current.isCurrent(controller)) return;
      setLogin(execution);
      const refreshed = await fetch("/api/connections/boss", { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]) });
      if (refreshed.ok) setConnection(await refreshed.json() as Connection);
      requestKey.current = null;
    } catch (failure) {
      if (!requests.current.isCurrent(controller)) return;
      if (!(failure instanceof Error)) throw failure;
      setNeedsReconciliation(true);
      setError("未能确认登录请求结果，请先重新读取连接状态；不会自动重试。");
    } finally {
      writing.current = false;
      if (requests.current.isCurrent(controller)) setBusy(null);
    }
  };

  const stopLogin = async () => {
    if (writing.current || busy || needsReconciliation || !connection) return;
    writing.current = true;
    const controller = requests.current.start();
    setBusy("stop");
    setError(null);
    try {
      const response = await fetch(`/api/connections/boss/${connection.id}/login`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version: connection.version }),
        signal: AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]),
      });
      if (!response.ok) throw new Error("Login outcome unconfirmed");
      const stopped = await response.json() as LoginExecution;
      setLogin(stopped);
      if (stopped.outcome === "browser_released") requestKey.current = null;
      writing.current = false;
      await load();
    } catch (failure) {
      if (!requests.current.isCurrent(controller)) return;
      if (!(failure instanceof Error)) throw failure;
      setNeedsReconciliation(true);
      setError("未能确认停止结果，请先重新读取登录状态；不会自动重试。");
    } finally {
      writing.current = false;
      if (requests.current.isCurrent(controller)) setBusy(null);
    }
  };

  const active = connection && !["revoked", "failed"].includes(connection.status);
  const browserReady = login?.attempt_status === "waiting" && login.outcome === "browser_created" && login.browser_session_id;
  const cleanupRequired = Boolean(login?.browser_session_id && login.outcome !== "browser_released");
  const viewerHref = browserReady ? `/api/browser/sessions/${login.browser_session_id}/viewer` : null;
  return <section aria-labelledby="boss-connection-title" className="mb-5 rounded-xl border bg-muted/20 p-5">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 id="boss-connection-title" className="text-sm font-medium">连接 BOSS 直聘</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">招聘沟通需要先在隔离浏览器中完成登录和安全验证。</p></div>
      <span role="status" className={cn("rounded-full px-2 py-1 text-[11px] font-medium", connection?.status === "connected" ? "bg-green-100 text-green-800 dark:bg-green-950 dark:text-green-200" : "bg-muted text-muted-foreground")}>
        {busy === "read" ? "读取连接状态" : needsReconciliation ? "状态待核对" : connection ? labels[connection.status] : "尚未连接"}
      </span>
    </div>
    <p className="mt-4 max-w-2xl text-xs leading-5 text-muted-foreground">密码、短信验证码和验证码只应由你在安全浏览器中输入，不会进入 Agent 对话或普通业务记录。</p>
    <p className="mt-2 max-w-2xl text-xs leading-5 text-muted-foreground">登录会在隔离浏览器中进行。CareerAct 不接收密码、短信验证码或验证码；完成登录后会继续停留在等待核验状态。</p>
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <Button disabled={busy !== null || needsReconciliation || loginAvailable === false || cleanupRequired || connection?.status === "connected"} variant="outline" onClick={() => void startLogin()}>
        {busy === "start" && <LoaderCircle className="size-3.5 animate-spin" />}{browserReady ? "等待登录" : active ? "开始安全登录" : "重新开始安全登录"}
      </Button>
      {viewerHref && <a className="inline-flex min-h-9 items-center gap-2 rounded-md border px-3 text-xs hover:bg-muted" href={viewerHref} target="_blank" rel="noreferrer"><ExternalLink className="size-3.5" />打开安全浏览器</a>}
      {cleanupRequired && <Button disabled={busy !== null || needsReconciliation} variant="ghost" onClick={() => void stopLogin()}>{busy === "stop" && <LoaderCircle className="size-3.5 animate-spin" />}停止登录</Button>}
      <Button disabled={busy !== null} variant="ghost" onClick={() => void load()}><RefreshCw className="size-3.5" />重新读取</Button>
    </div>
    {loginAvailable === false && <p role="status" className="mt-3 text-xs text-amber-700 dark:text-amber-300">安全登录服务尚未配置；当前不会启动浏览器。配置 Browser Service 后重新读取即可。</p>}
    {error && <p role="alert" className="mt-3 text-xs text-destructive">{error}</p>}
  </section>;
}

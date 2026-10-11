"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronUp, Maximize2, Minimize2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";

type ViewerStatus = "loading" | "connected" | "disconnected" | "error";

const MIN_VIEWER_HEIGHT = 320;
const MAX_VIEWER_HEIGHT = 720;
const EXPANDED_VIEWER_HEIGHT = 640;

const statusLabels: Record<ViewerStatus, string> = {
  loading: "正在加载现场",
  connected: "现场连接中",
  disconnected: "现场已断开",
  error: "现场连接异常",
};

export function BrowserScene({ sessionId, allowLoginControl = false }: { sessionId: string; allowLoginControl?: boolean }) {
  const [collapsed, setCollapsed] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [status, setStatus] = useState<ViewerStatus>("loading");
  const [height, setHeight] = useState<number | null>(null);
  const [reloadCount, setReloadCount] = useState(0);
  const [mode, setMode] = useState<"watch" | "control">("watch");
  const frame = useRef<HTMLIFrameElement>(null);
  const resizeOrigin = useRef<{ y: number; height: number } | null>(null);
  const viewerUrl = `/api/browser/sessions/${sessionId}/viewer?mode=${mode}`;

  useEffect(() => {
    const receiveStatus = (event: MessageEvent<unknown>) => {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow || !event.data || typeof event.data !== "object") return;
      const message = event.data as { source?: string; sessionId?: string; mode?: string; status?: ViewerStatus };
      if (message.source !== "careeract-browser-viewer" || message.sessionId !== sessionId || message.mode !== mode) return;
      if (message.status && message.status in statusLabels) setStatus(message.status);
    };
    const timeout = setTimeout(() => setStatus(current => current === "loading" ? "error" : current), 20_000);
    window.addEventListener("message", receiveStatus);
    return () => {
      clearTimeout(timeout);
      window.removeEventListener("message", receiveStatus);
    };
  }, [sessionId, reloadCount, mode]);

  const resize = (clientY: number) => {
    const origin = resizeOrigin.current;
    if (!origin) return;
    setHeight(Math.min(MAX_VIEWER_HEIGHT, Math.max(MIN_VIEWER_HEIGHT, origin.height + clientY - origin.y)));
  };

  return <section aria-label="浏览器现场" className="mb-5 overflow-hidden rounded-xl border bg-background">
    <div className="flex min-h-11 items-center justify-between gap-3 border-b px-4 py-2">
      <div className="min-w-0"><h3 className="text-xs font-medium">{mode === "control" ? "浏览器现场 · 人工登录" : "浏览器现场 · 只读观看"}</h3><p className="mt-0.5 text-[11px] text-muted-foreground">{mode === "control" ? "当前由你操作。控制连接被服务端独占；完成后保存登录。" : "观看不会获得输入权，也不会改变远端页面尺寸。"}</p></div>
      <div className="flex shrink-0 items-center gap-1">
        {allowLoginControl && <Button variant="outline" size="sm" onClick={() => { setStatus("loading"); setCollapsed(false); setMode(value => value === "watch" ? "control" : "watch"); }}>{mode === "control" ? "返回观看" : "操作登录浏览器"}</Button>}
        {(status === "error" || status === "disconnected") && <Button variant="ghost" size="icon-xs" aria-label="重新连接浏览器现场" title="重新连接" onClick={() => { setStatus("loading"); setReloadCount(value => value + 1); }}><RefreshCw /></Button>}
        <Button variant="ghost" size="icon-xs" aria-label={expanded ? "缩小浏览器现场" : "展开浏览器现场"} title={expanded ? "缩小" : "展开"} onClick={() => { setCollapsed(false); setExpanded(value => !value); setHeight(value => value === null ? (expanded ? null : EXPANDED_VIEWER_HEIGHT) : value); }}>{expanded ? <Minimize2 /> : <Maximize2 />}</Button>
        <Button variant="ghost" size="icon-xs" aria-label={collapsed ? "展开浏览器现场" : "折叠浏览器现场"} title={collapsed ? "展开" : "折叠"} onClick={() => setCollapsed(value => !value)}>{collapsed ? <ChevronDown /> : <ChevronUp />}</Button>
      </div>
    </div>
    <div className="relative bg-muted/20 transition-[height] duration-200" style={{ height: collapsed ? 0 : (height ?? (expanded ? EXPANDED_VIEWER_HEIGHT : undefined)), aspectRatio: collapsed || height !== null || expanded ? undefined : "16 / 9", maxHeight: collapsed ? 0 : MAX_VIEWER_HEIGHT, minHeight: collapsed ? 0 : MIN_VIEWER_HEIGHT, overflow: "hidden" }} aria-hidden={collapsed}>
      <iframe ref={frame} key={`${sessionId}:${mode}:${reloadCount}`} title={mode === "control" ? "人工登录浏览器" : "浏览器现场"} src={viewerUrl} onError={() => setStatus("error")} className="absolute inset-0 size-full border-0" />
      {status !== "connected" && <div role="status" className="pointer-events-none absolute bottom-2 left-2 rounded-md bg-background/90 px-2 py-1 text-[11px] text-muted-foreground shadow-sm">{statusLabels[status]}</div>}
    </div>
    {!collapsed && <div role="separator" aria-label="调整浏览器现场高度" aria-orientation="horizontal" aria-valuemin={MIN_VIEWER_HEIGHT} aria-valuemax={MAX_VIEWER_HEIGHT} aria-valuenow={height ?? (expanded ? EXPANDED_VIEWER_HEIGHT : 548)} tabIndex={0} className="group relative z-10 h-2 cursor-row-resize touch-none bg-muted/20 outline-none focus-visible:ring-2 focus-visible:ring-ring" onKeyDown={event => { if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return; event.preventDefault(); setHeight(value => Math.min(MAX_VIEWER_HEIGHT, Math.max(MIN_VIEWER_HEIGHT, (value ?? (expanded ? EXPANDED_VIEWER_HEIGHT : 548)) + (event.key === "ArrowDown" ? 24 : -24)))); }} onPointerDown={event => { event.currentTarget.setPointerCapture(event.pointerId); resizeOrigin.current = { y: event.clientY, height: height ?? (expanded ? EXPANDED_VIEWER_HEIGHT : 548) }; }} onPointerMove={event => resize(event.clientY)} onPointerUp={event => { resize(event.clientY); resizeOrigin.current = null; }} onPointerCancel={() => { resizeOrigin.current = null; }}><span className="absolute inset-x-1/2 top-1/2 h-0.5 w-12 -translate-x-1/2 -translate-y-1/2 rounded-full bg-border transition-colors group-hover:bg-primary/60 group-focus-visible:bg-primary/60" /></div>}
    <div className="flex min-h-9 items-center justify-between gap-3 border-t px-4 py-1.5 text-[11px] text-muted-foreground"><span>{statusLabels[status]}</span><span className="inline-flex items-center gap-1"><RefreshCw className="size-3" />关闭现场不会停止登录任务</span></div>
  </section>;
}

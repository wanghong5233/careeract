"use client";

import { useCallback, useEffect, useState } from "react";
import { createLatestRequest } from "@/lib/latest-request";
import { generateConversationTitle, readConversationHistory, type ConversationHistory } from "@/lib/agent-conversations";
import { activeConversationRun } from "@/lib/agent-runtime";

export function useConversationHistory(id: string, persisted: boolean) {
  const [result, setResult] = useState<{ id: string; history: ConversationHistory | null; error: string; loading: boolean } | null>(null);
  const [requests] = useState(createLatestRequest);
  const load = useCallback(async () => {
    const controller = requests.start();
    if (!persisted) return;
    try {
      const history = await readConversationHistory(id, AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]));
      if (requests.isCurrent(controller)) setResult({ id, history, error: "", loading: false });
    } catch (failure) {
      if (requests.isCurrent(controller)) setResult({ id, history: null, error: failure instanceof Error ? failure.message : "历史读取失败，请重试。", loading: false });
    }
  }, [id, persisted, requests]);
  useEffect(() => {
    const refresh = () => { void load(); };
    queueMicrotask(refresh);
    window.addEventListener("focus", refresh);
    return () => { requests.cancel(); window.removeEventListener("focus", refresh); };
  }, [load, requests]);
  const visible = result?.id === id && persisted ? result : null;
  const activeRun = activeConversationRun(visible?.history?.runs);
  const activeRunId = activeRun?.run_id;
  const naming = visible?.history;
  useEffect(() => {
    if (!naming || naming.session.title_origin !== "default" || naming.session.title_generation_attempted || !naming.messages.some(message => message.role === "user" && message.run_status === "COMPLETED")) return;
    const controller = new AbortController();
    void generateConversationTitle(naming.session, AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)])).then(session => {
      if (controller.signal.aborted) return;
      setResult(previous => previous?.id === id && previous.history?.session.version === naming.session.version ? { ...previous, history: { ...previous.history, session } } : previous);
      window.dispatchEvent(new Event("careeract:conversations-changed"));
    }).catch((failure: unknown) => {
      if (controller.signal.aborted) return;
      if (!(failure instanceof Error)) throw failure;
      window.dispatchEvent(new Event("careeract:conversations-changed"));
    });
    return () => controller.abort();
  }, [id, naming]);
  useEffect(() => {
    if (!activeRunId) return;
    const timer = setInterval(() => { void load(); }, 2000);
    return () => clearInterval(timer);
  }, [activeRunId, load]);
  return { history: visible?.history ?? null, activeRun, error: visible?.error ?? "", loading: persisted && (visible?.loading ?? true), refresh: () => {
    setResult({ id, history: null, error: "", loading: true });
    return load();
  } };
}

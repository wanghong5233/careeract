"use client";

import { useCallback, useEffect, useState } from "react";
import { createLatestRequest } from "@/lib/latest-request";
import { readConversationHistory, type ConversationHistory } from "@/lib/agent-conversations";

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
  return { history: visible?.history ?? null, error: visible?.error ?? "", loading: persisted && (visible?.loading ?? true), refresh: () => {
    setResult({ id, history: null, error: "", loading: true });
    return load();
  } };
}

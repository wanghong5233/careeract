"use client";

import { useCallback, useEffect, useState } from "react";
import { createLatestRequest } from "@/lib/latest-request";
import { getSpaceStore, mergeSpaceConversations } from "@/lib/agent-space-state";
import { createConversation, readConversations, saveConversation, type AgentConversation } from "@/lib/agent-conversations";

export function useAgentConversations(owner: string) {
  const store = getSpaceStore(owner);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [requests] = useState(createLatestRequest);

  const load = useCallback(async (nextCursor?: string) => {
    const controller = requests.start();
    setLoading(true); setError("");
    try {
      const page = await readConversations(nextCursor, AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]));
      if (!requests.isCurrent(controller)) return;
      store.update(state => mergeSpaceConversations(state, page.items));
      setCursor(page.next_cursor);
    } catch (failure) {
      if (requests.isCurrent(controller)) setError(failure instanceof Error ? failure.message : "对话读取失败，请重试。");
    } finally { if (requests.isCurrent(controller)) setLoading(false); }
  }, [requests, store]);

  useEffect(() => {
    const refresh = () => { void load(); };
    const focus = () => { refresh(); };
    refresh();
    window.addEventListener("careeract:conversations-changed", refresh);
    window.addEventListener("careeract:projects-changed", refresh);
    window.addEventListener("focus", focus);
    return () => {
      requests.cancel();
      window.removeEventListener("careeract:conversations-changed", refresh);
      window.removeEventListener("careeract:projects-changed", refresh);
      window.removeEventListener("focus", focus);
    };
  }, [load, requests]);

  function accept(saved: AgentConversation, replaceId?: string) {
    requests.cancel(); setLoading(false);
    store.update(state => {
      const previous = state.conversations.find(item => item.id === replaceId);
      const mapped = previous && replaceId !== saved.session_id ? {
        ...state, selectedId: state.selectedId === replaceId ? saved.session_id : state.selectedId,
        conversations: state.conversations.map(item => item.id === replaceId ? { ...item, id: saved.session_id } : item),
      } : state;
      return mergeSpaceConversations(mapped, [saved]);
    });
  }

  async function persist(id: string, changes: { title?: string; project_id?: string | null; archived?: boolean } = {}) {
    const local = store.snapshot().conversations.find(item => item.id === id);
    if (!local) throw new Error("找不到该对话，请重新读取。");
    let saved: AgentConversation;
    if (local.version) saved = await saveConversation(local.id, local.version, changes);
    else {
      const createId = local.createId ?? crypto.randomUUID();
      store.update(state => ({ ...state, conversations: state.conversations.map(item => item.id === id ? { ...item, createId } : item) }));
      saved = await createConversation(createId, local.title, local.projectId);
      accept(saved, id);
      if (Object.keys(changes).length) saved = await saveConversation(saved.session_id, saved.version, changes);
    }
    accept(saved, id);
    return saved;
  }

  return { loading, error, cursor, accept, persist, refresh: () => load(), loadMore: () => cursor ? load(cursor) : Promise.resolve() };
}

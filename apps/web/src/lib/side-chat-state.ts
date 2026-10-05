import type { SideChat } from "@/lib/agent-conversations";

export type SideChatView = { chat: SideChat | null; tabId: string; draft: string; hidden: boolean; suppressCloseWarning: boolean; mainCheckpoint?: string | null };
const stores = new Map<string, ReturnType<typeof createSideChatStore>>();
const empty: SideChatView = { chat: null, tabId: "", draft: "", hidden: true, suppressCloseWarning: false };

export function readSideChatView(value: string | null): SideChatView {
  if (!value) return empty;
  try {
    const parsed = JSON.parse(value) as SideChatView;
    if (!parsed || typeof parsed.tabId !== "string" || typeof parsed.draft !== "string" || typeof parsed.hidden !== "boolean" || typeof parsed.suppressCloseWarning !== "boolean") return empty;
    if (parsed.chat && (typeof parsed.chat.session_id !== "string" || !parsed.chat.session_id.startsWith("side:") || typeof parsed.chat.side_context?.source_id !== "string" || typeof parsed.chat.temporary_until !== "string")) return empty;
    return parsed;
  } catch (failure) { if (!(failure instanceof SyntaxError)) throw failure; return empty; }
}

function createSideChatStore(owner: string) {
  const key = `careeract-side:${owner}`;
  let state = empty;
  let available = true;
  const listeners = new Set<() => void>();
  function update(change: (previous: SideChatView) => SideChatView) {
    state = change(state);
    try { sessionStorage.setItem(key, JSON.stringify(state)); } catch (failure) { if (!(failure instanceof DOMException)) throw failure; available = false; }
    listeners.forEach(listener => listener());
  }
  if (typeof window !== "undefined") {
    try { state = readSideChatView(sessionStorage.getItem(key)); } catch (failure) { if (!(failure instanceof DOMException)) throw failure; available = false; }
    if (!state.tabId) state = { ...state, tabId: crypto.randomUUID() };
  }
  return { snapshot: () => state, serverSnapshot: () => empty, subscribe: (listener: () => void) => { listeners.add(listener); return () => { listeners.delete(listener); }; }, update, storageAvailable: () => available };
}

export function getSideChatStore(owner: string) {
  if (typeof window === "undefined") return createSideChatStore(owner);
  let store = stores.get(owner);
  if (!store) { store = createSideChatStore(owner); stores.set(owner, store); }
  return store;
}

export function appendSideQuote(draft: string, quote: string): string {
  return quote ? `${draft}${draft ? "\n\n" : ""}> ${quote.split("\n").join("\n> ")}\n\n` : draft;
}

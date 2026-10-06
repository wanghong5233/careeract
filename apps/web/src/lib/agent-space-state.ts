export type SpaceTab = { href: string; label: string };
import type { AgentConversation } from "@/lib/agent-conversations";

export type SpaceConversation = { id: string; projectId: string | null; title: string; draft: string; archived: boolean; tabs: SpaceTab[]; activeHref: string; panelHidden: boolean; version?: string; createId?: string; modelId?: string | null; titleOrigin?: string; titleGenerationAttempted?: boolean };
export type SpaceState = { conversations: SpaceConversation[]; selectedId: string; navigation: boolean; panelWidth: number };
export function newSpaceConversation(id: string, projectId: string | null = null): SpaceConversation {
  return { id, projectId, title: "新对话", draft: "", archived: false, tabs: [], activeHref: "/workspace", panelHidden: false };
}

export function beginSpaceConversation(state: SpaceState, id: string, projectId: string | null = null): SpaceState {
  const empty = state.conversations.find(item => !item.version && !item.archived && !item.draft && item.title === "新对话" && item.projectId === projectId && !item.tabs.length);
  const conversation = { ...newSpaceConversation(empty?.id ?? id, projectId), panelHidden: true };
  return {
    ...state,
    selectedId: conversation.id,
    conversations: empty ? state.conversations.map(item => item.id === empty.id ? conversation : item) : [conversation, ...state.conversations],
  };
}

export function removeSpaceConversation(state: SpaceState, id: string): SpaceState {
  const conversations = state.conversations.filter(item => item.id !== id);
  if (state.selectedId !== id) return { ...state, conversations };
  const blank = newSpaceConversation(crypto.randomUUID());
  return { ...state, conversations: [blank, ...conversations], selectedId: blank.id };
}

export function mergeSpaceConversations(state: SpaceState, conversations: AgentConversation[]): SpaceState {
  const local = new Map(state.conversations.map(item => [item.id, item]));
  const remoteIds = new Set(conversations.map(item => item.session_id));
  const merged = conversations.map(item => ({
    ...newSpaceConversation(item.session_id), ...local.get(item.session_id),
    id: item.session_id, title: item.title, projectId: item.project_id,
    archived: item.archived, version: item.version,
    modelId: item.model_id, titleOrigin: item.title_origin, titleGenerationAttempted: item.title_generation_attempted,
  }));
  return { ...state, conversations: [...merged, ...state.conversations.filter(item => !remoteIds.has(item.id))] };
}
const initialState: SpaceState = { conversations: [newSpaceConversation("new")], selectedId: "new", navigation: true, panelWidth: 50 };

export function removeSpaceProject(state: SpaceState, projectId: string): SpaceState {
  const href = `/workspace/projects/${projectId}`;
  return {
    ...state,
    conversations: state.conversations.map(item => ({
      ...item,
      projectId: item.projectId === projectId ? null : item.projectId,
      tabs: item.tabs.filter(tab => tab.href.split(/[?#]/)[0] !== href),
      activeHref: item.activeHref.split(/[?#]/)[0] === href ? "/workspace" : item.activeHref,
      panelHidden: item.activeHref.split(/[?#]/)[0] === href ? true : item.panelHidden,
    })),
  };
}
const stores = new Map<string, ReturnType<typeof createStore>>();
const storagePrefix = "careeract-space:";

function validTabs(value: unknown): value is SpaceTab[] {
  return Array.isArray(value) && value.every(tab => tab && typeof tab.href === "string" && tab.href.startsWith("/workspace/") && !tab.href.includes("\\") && typeof tab.label === "string");
}

function isSpaceState(value: unknown): value is SpaceState & { tabs?: SpaceTab[] } {
  if (!value || typeof value !== "object") return false;
  const state = value as SpaceState & { tabs?: SpaceTab[] };
  return typeof state.selectedId === "string" && typeof state.navigation === "boolean"
    && typeof state.panelWidth === "number" && state.panelWidth >= 30 && state.panelWidth <= 65
    && Array.isArray(state.conversations) && state.conversations.length > 0
    && state.conversations.every(item => item && typeof item.id === "string"
      && (item.projectId === null || typeof item.projectId === "string")
      && typeof item.title === "string" && typeof item.draft === "string" && typeof item.archived === "boolean"
      && (item.version === undefined || typeof item.version === "string")
      && (item.createId === undefined || typeof item.createId === "string")
      && (item.tabs === undefined || validTabs(item.tabs))
      && (item.activeHref === undefined || item.activeHref === "/workspace" || (typeof item.activeHref === "string" && item.activeHref.startsWith("/workspace/") && !item.activeHref.includes("\\")))
      && (item.panelHidden === undefined || typeof item.panelHidden === "boolean"))
    && state.conversations.some(item => item.id === state.selectedId)
    && (state.tabs === undefined || validTabs(state.tabs));
}

function createStore(owner: string) {
  let snapshot = initialState;
  let loaded = false;
  let storageAvailable = true;
  const listeners = new Set<() => void>();
  return {
    subscribe(listener: () => void) { listeners.add(listener); return () => { listeners.delete(listener); }; },
    serverSnapshot: () => initialState,
    snapshot() {
      if (!loaded && typeof window !== "undefined") {
        loaded = true;
        try {
          const raw = sessionStorage.getItem(storagePrefix + owner);
          const parsed: unknown = raw ? JSON.parse(raw) : null;
          if (isSpaceState(parsed)) snapshot = {
            selectedId: parsed.selectedId, navigation: parsed.navigation, panelWidth: parsed.panelWidth,
            conversations: parsed.conversations.map(item => ({ ...newSpaceConversation(item.id, item.projectId), ...item, tabs: item.tabs ?? (item.id === parsed.selectedId ? parsed.tabs ?? [] : []) })),
          };
        } catch { storageAvailable = false; }
      }
      return snapshot;
    },
    update(change: (state: SpaceState) => SpaceState) {
      const next = change(snapshot);
      if (next === snapshot) return;
      snapshot = next;
      try { sessionStorage.setItem(storagePrefix + owner, JSON.stringify(snapshot)); storageAvailable = true; }
      catch { storageAvailable = false; }
      listeners.forEach(listener => listener());
    },
    storageAvailable: () => storageAvailable,
  };
}

export function getSpaceStore(owner: string) {
  let store = stores.get(owner);
  if (!store) { store = createStore(owner); stores.set(owner, store); }
  return store;
}

export function clearSpaceDrafts() {
  stores.clear();
  for (let index = sessionStorage.length - 1; index >= 0; index--) {
    const key = sessionStorage.key(index);
    if (key?.startsWith(storagePrefix)) sessionStorage.removeItem(key);
  }
}

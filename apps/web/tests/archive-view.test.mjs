import assert from "node:assert/strict";
import test from "node:test";
import * as React from "react";
import { loadSource } from "./load-source.mjs";

function elements(value) {
  if (Array.isArray(value)) return value.flatMap(elements);
  if (!React.isValidElement(value)) return [];
  return [value, ...elements(value.props.children)];
}

function view(archived) {
  const conversation = { id: "synthetic", title: "合成归档验收", projectId: null, archived, version: "v1", draft: "保留草稿", tabs: [], activeHref: "/", panelHidden: false };
  const state = { conversations: [conversation], selectedId: conversation.id, navigation: true, panelWidth: 50 };
  const store = { snapshot: () => state, subscribe: () => () => {}, serverSnapshot: () => state, update: () => {}, storageAvailable: () => true };
  const Placeholder = () => null;
  const dependencies = {
    react: { ...React, useCallback: callback => callback, useEffect: () => {}, useRef: current => ({ current }), useState: current => [current, () => {}], useSyncExternalStore: (_subscribe, snapshot) => snapshot() },
    "next/navigation": { usePathname: () => "/", useRouter: () => ({ push: () => {} }), useSearchParams: () => new URLSearchParams() },
    "@assistant-ui/react": { useAui: () => ({}), useAuiState: selector => selector({ thread: { isRunning: false, messages: [] } }) },
    "@/components/ui/button": { Button: Placeholder },
    "@/components/ui/dialog": { Dialog: Placeholder, DialogContent: Placeholder, DialogDescription: Placeholder, DialogHeader: Placeholder, DialogTitle: Placeholder },
    "@/components/ui/collapsible": { Collapsible: Placeholder, CollapsibleContent: Placeholder, CollapsibleTrigger: Placeholder },
    "@/components/workspace-account": { AccountButton: Placeholder },
    "@/components/agent-composer-tools": { AgentComposerTools: Placeholder },
    "@/components/agent-project-picker": { AgentProjectPicker: Placeholder },
    "@/components/conversation-history": { ConversationHistory: function History() {} },
    "@/components/side-chat": { useSideChat: () => ({ state: { chat: null, hidden: true }, store, busy: false }), SideChatPanel: Placeholder },
    "@/components/tooltip-icon-button": { TooltipIconButton: Placeholder },
    "@/components/workspace-actions": { useWorkspaceActions: () => ({}) },
    "@/components/workspace-sections": { workspaceSections: [], navigationHref: () => "/" },
    "@/lib/agent-space-state": { getSpaceStore: () => store },
    "@/lib/projects": {},
    "@/hooks/use-project-list": { useProjectList: () => ({ projects: [] }) },
    "@/hooks/use-agent-conversations": { useAgentConversations: () => ({}) },
    "@/hooks/use-conversation-history": { useConversationHistory: () => ({ history: { session: {}, messages: [{ id: "user", role: "user", text: "合成历史", run_status: "COMPLETED" }] } }) },
    "@/lib/utils": { cn: () => "" },
    "@/lib/agent-runtime": {},
    "@/lib/agent-conversations": {},
    "@/lib/conversation-selection": {},
    "./agent-space.module.css": { default: {} },
  };
  const { AgentHome } = loadSource("components/agent-space.tsx", dependencies);
  return elements(AgentHome({ owner: "synthetic-owner" }));
}

test("archived history has no composer or conversation mutations and keeps an explicit restore action", () => {
  const archived = view(true);
  assert.equal(archived.some(element => element.type === "textarea"), false);
  assert.equal(archived.some(element => element.props.children?.includes?.("恢复并继续对话")), true);
  const history = archived.find(element => element.type.name === "History");
  for (const action of ["onQuote", "onEdit", "onBranch", "onAddToConversation"]) assert.equal(history.props[action], undefined);
  assert.equal(archived.find(element => element.props["aria-label"] === "打开临时侧聊").props.disabled, true);
  const active = view(false);
  assert.equal(active.some(element => element.type === "textarea" && element.props.value === "保留草稿"), true);
  assert.equal(typeof active.find(element => element.type.name === "History").props.onQuote, "function");
});

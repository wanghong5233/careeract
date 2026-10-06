"use client";

import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { RuntimeProvider } from "@/app/runtime-provider";
import { AgentHome } from "@/components/agent-space";
import { getSpaceStore } from "@/lib/agent-space-state";
import { conversationRuntimeKey } from "@/lib/agent-runtime";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { WorkspaceActionsContext, useWorkspaceActions } from "@/components/workspace-actions";
import { WorkspaceAccount } from "@/components/workspace-account";
import { navigationHref, workspaceGroups, workspaceSections } from "@/components/workspace-sections";

function CapabilitySearch({ open, onOpenChange }: { open: boolean; onOpenChange: (value: boolean) => void }) {
  const { openContent } = useWorkspaceActions();
  const [query, setQuery] = useState("");
  const normalized = query.trim().toLocaleLowerCase();
  const results = workspaceSections.filter(item => (item.label + " " + item.description + " " + item.key + " " + (item.keywords ?? "")).toLocaleLowerCase().includes(normalized));
  const resultList = useRef<HTMLElement>(null);
  function choose(href: string) { onOpenChange(false); setQuery(""); openContent(href); }
  return <Dialog open={open} onOpenChange={value => { onOpenChange(value); if (!value) setQuery(""); }}>
    <DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-2xl">
      <DialogHeader className="px-5 pb-3 pt-5"><DialogTitle>搜索能力</DialogTitle><DialogDescription className="sr-only">输入关键词筛选，使用上下方向键选择，Enter 打开。</DialogDescription></DialogHeader>
      <div className="flex items-center gap-3 border-y px-5"><Search className="size-4 text-muted-foreground" /><input autoFocus value={query} onChange={event => setQuery(event.target.value)} aria-label="搜索全部能力" placeholder="搜索材料、岗位、申请…" className="h-12 min-w-0 flex-1 bg-transparent text-sm outline-none" onKeyDown={event => {
        if (event.nativeEvent.isComposing) return;
        const links = resultList.current?.querySelectorAll<HTMLAnchorElement>("a");
        if (!links?.length) return;
        if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); links[event.key === "ArrowDown" ? 0 : links.length - 1].focus(); }
        if (event.key === "Enter") { event.preventDefault(); links[0].click(); }
      }} /></div>
      <nav ref={resultList} aria-label="全部能力" className="max-h-[60dvh] overflow-y-auto p-3" onKeyDown={event => {
        if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
        const links = Array.from(event.currentTarget.querySelectorAll<HTMLAnchorElement>("a"));
        const currentIndex = links.indexOf(document.activeElement as HTMLAnchorElement);
        if (currentIndex < 0) return;
        event.preventDefault();
        const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? links.length - 1 : (currentIndex + (event.key === "ArrowDown" ? 1 : -1) + links.length) % links.length;
        links[nextIndex]?.focus();
      }}>
        {workspaceGroups.map(group => { const items = results.filter(item => item.group === group); return items.length > 0 && <div key={group} className="mb-3"><p className="px-2 py-2 text-xs text-muted-foreground">{group}</p><div className="grid gap-1">{items.map(item => { const Icon = item.icon; return <Link id={"capability-" + item.key} key={item.key} href={navigationHref(item.key)} onClick={event => { if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); choose(navigationHref(item.key)); } }} className="flex items-center gap-3 rounded-lg p-2.5 outline-none hover:bg-muted focus-visible:bg-muted focus-visible:ring-2 focus-visible:ring-ring"><Icon className="size-4 shrink-0 text-muted-foreground" /><div className="min-w-0"><p className="text-sm font-medium">{item.label}</p><p className="mt-0.5 text-xs text-muted-foreground">{item.description}</p></div></Link>; })}</div></div>; })}
        {!results.length && <p role="status" className="p-8 text-center text-sm text-muted-foreground">没有匹配的能力。试试公司、面试或材料等关键词。</p>}
      </nav>
    </DialogContent>
  </Dialog>;
}

export function WorkspaceFrame({ children, agentThreadId }: Readonly<{ children: ReactNode; agentThreadId: string }>) {
  const store = getSpaceStore(agentThreadId);
  const state = useSyncExternalStore(store.subscribe, store.snapshot, store.serverSnapshot);
  const selected = state.conversations.find(item => item.id === state.selectedId);
  const conversationId = selected?.version ? selected.id : undefined;
  const runtimeKey = conversationRuntimeKey(conversationId, selected?.id);
  return <RuntimeProvider key={runtimeKey} agentThreadId={conversationId}><WorkspaceFrameContent owner={agentThreadId}>{children}</WorkspaceFrameContent></RuntimeProvider>;
}

function WorkspaceFrameContent({ children, owner }: { children: ReactNode; owner: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [capabilitiesOpen, setCapabilitiesOpen] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const agentHandler = useRef<((prompt?: string) => void) | null>(null);
  const contentHandler = useRef<((href: string) => void) | null>(null);
  const descriptionHandler = useRef<((content: { href: string; label: string }) => void) | null>(null);
  const actions = useMemo(() => ({
    openAgent: (prompt?: string) => agentHandler.current?.(prompt),
    openContent: (href: string) => {
      setCapabilitiesOpen(false);
      if (contentHandler.current) contentHandler.current(href);
      else router.push(href);
    },
    openCapabilities: () => setCapabilitiesOpen(true),
    openAccount: () => setAccountOpen(true),
    registerAgent: (handler: (prompt?: string) => void) => { agentHandler.current = handler; return () => { if (agentHandler.current === handler) agentHandler.current = null; }; },
    registerContent: (handler: (href: string) => void) => { contentHandler.current = handler; return () => { if (contentHandler.current === handler) contentHandler.current = null; }; },
    describeContent: (content: { href: string; label: string }) => descriptionHandler.current?.(content),
    registerContentDescription: (handler: (content: { href: string; label: string }) => void) => { descriptionHandler.current = handler; return () => { if (descriptionHandler.current === handler) descriptionHandler.current = null; }; },
  }), [router]);

  useEffect(() => {
    function shortcut(event: KeyboardEvent) {
      if (event.isComposing) return;
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setCapabilitiesOpen(value => !value); }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  return <WorkspaceActionsContext.Provider value={actions}>
    <AgentHome owner={owner}>{pathname === "/" || pathname === "/workspace" ? null : children}</AgentHome>
    <CapabilitySearch open={capabilitiesOpen} onOpenChange={setCapabilitiesOpen} />
    <WorkspaceAccount open={accountOpen} onOpenChange={setAccountOpen} />
  </WorkspaceActionsContext.Provider>;
}

"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Search } from "lucide-react";
import { RuntimeProvider } from "@/app/runtime-provider";
import { AgentHome } from "@/components/agent-space";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { WorkspaceActionsContext, useWorkspaceActions } from "@/components/workspace-actions";
import { WorkspaceAccount } from "@/components/workspace-account";
import { navigationHref, workspaceGroups, workspaceSections } from "@/components/workspace-sections";

function CapabilitySearch({ open, onOpenChange }: { open: boolean; onOpenChange: (value: boolean) => void }) {
  const { openContent } = useWorkspaceActions();
  const [query, setQuery] = useState("");
  const normalized = query.trim().toLocaleLowerCase();
  const results = workspaceSections.filter(item => (item.label + " " + item.description + " " + item.key + " " + (item.keywords ?? "")).toLocaleLowerCase().includes(normalized));
  function choose(href: string) { onOpenChange(false); setQuery(""); openContent(href); }
  return <Dialog open={open} onOpenChange={value => { onOpenChange(value); if (!value) setQuery(""); }}>
    <DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-2xl">
      <DialogHeader className="px-5 pb-3 pt-5"><DialogTitle>职业能力</DialogTitle><DialogDescription>搜索要做的事，或查看 CareerAct 的 20 项能力范围。具体可用状态见各项内容。</DialogDescription></DialogHeader>
      <div className="flex items-center gap-3 border-y px-5"><Search className="size-4 text-muted-foreground" /><input autoFocus value={query} onChange={event => setQuery(event.target.value)} aria-label="搜索全部能力" placeholder="申请记录、面经、简历、规则…" className="h-12 min-w-0 flex-1 bg-transparent text-sm outline-none" onKeyDown={event => { if (event.key === "Enter" && results.length === 1) { event.preventDefault(); choose(navigationHref(results[0].key)); } }} /></div>
      <nav aria-label="全部能力" className="max-h-[60dvh] overflow-y-auto p-3">
        {workspaceGroups.map(group => { const items = results.filter(item => item.group === group); return items.length > 0 && <div key={group} className="mb-3"><p className="px-2 py-2 text-xs text-muted-foreground">{group}</p><div className="grid gap-1 sm:grid-cols-2">{items.map(item => { const Icon = item.icon; return <Link id={"capability-" + item.key} key={item.key} href={navigationHref(item.key)} onClick={event => { if (!event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) { event.preventDefault(); choose(navigationHref(item.key)); } }} className="flex items-center gap-3 rounded-lg p-2.5 outline-none hover:bg-muted focus-visible:bg-muted focus-visible:ring-2 focus-visible:ring-ring"><Icon className="size-4 shrink-0 text-muted-foreground" /><div className="min-w-0"><p className="text-sm font-medium">{item.label}</p><p className="mt-0.5 text-xs text-muted-foreground">{item.description}</p></div></Link>; })}</div></div>; })}
        {!results.length && <p role="status" className="p-8 text-center text-sm text-muted-foreground">没有匹配的能力。试试公司、面试或材料等关键词。</p>}
      </nav>
    </DialogContent>
  </Dialog>;
}

export function WorkspaceFrame({ children, agentThreadId }: Readonly<{ children: ReactNode; agentThreadId: string }>) {
  return <RuntimeProvider agentThreadId={agentThreadId}><WorkspaceFrameContent owner={agentThreadId}>{children}</WorkspaceFrameContent></RuntimeProvider>;
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
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setCapabilitiesOpen(value => !value); }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  return <WorkspaceActionsContext.Provider value={actions}>
    <AgentHome owner={owner}>{pathname === "/workspace" ? null : children}</AgentHome>
    <CapabilitySearch open={capabilitiesOpen} onOpenChange={setCapabilitiesOpen} />
    <WorkspaceAccount open={accountOpen} onOpenChange={setAccountOpen} />
  </WorkspaceActionsContext.Provider>;
}

"use client";

import { useEffect, useState, useSyncExternalStore, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAui, useAuiState } from "@assistant-ui/react";
import { Bird, ChevronDown, ChevronRight, FolderKanban, LogOut, Menu, PanelRight, Search, X } from "lucide-react";

import { RuntimeProvider } from "@/app/runtime-provider";
import { Thread } from "@/components/thread.aui";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { WorkspaceActionsContext } from "@/components/workspace-actions";
import { navigationHref, workspaceGroups, workspaceSections } from "@/components/workspace-sections";
import { authClient } from "@/lib/auth-client";
import { cn } from "@/lib/utils";

function subscribeDesktop(onChange: () => void) {
  const query = window.matchMedia("(min-width: 1024px)");
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

function desktopSnapshot() {
  return window.matchMedia("(min-width: 1024px)").matches;
}

function AgentWelcome() {
  return <div className="space-y-3 px-1 text-left"><Bird className="mb-5 size-7" /><h2 className="text-lg font-medium tracking-tight">一起把下一步做清楚。</h2><p className="text-sm leading-6 text-muted-foreground">说说目标、贴一段内容，或告诉我哪里需要调整。你提供判断，我协助整理和创作。</p><p className="text-xs leading-5 text-muted-foreground">刷新后会继续同一伙伴会话，已保存的文本历史按登录用户恢复。工作区读取、成果保存和外部动作仍待接入。</p></div>;
}

function AgentDock({ currentLabel, onClose }: { currentLabel: string; onClose: () => void }) {
  const running = useAuiState(state => state.thread.isRunning);
  return <div id="career-agent" className="flex h-full min-h-0 flex-col bg-background">
    <div className="flex h-16 shrink-0 items-center justify-between border-b px-5">
      <div className="flex items-center gap-2.5"><Bird className="size-5" /><div><p className="text-sm font-medium">渡鸦</p><p role="status" className="text-xs text-muted-foreground">{running ? "正在回应 · 可停止" : "职业伙伴 · 等待你的委托"}</p></div></div>
      <Button variant="ghost" size="icon" onClick={onClose} aria-label="收起职业伙伴"><X className="size-4" /></Button>
    </div>
    <div className="border-b px-5 py-3 text-xs text-muted-foreground">正在查看：<span className="text-foreground">{currentLabel}</span><p className="mt-1">页面内容尚未自动带入对话</p><p className="mt-2 leading-5">保存的职业资料在服务端；发送的内容会交给已配置的模型服务。请勿提供证件号、密码或验证码。</p></div>
    <div className="min-h-0 flex-1"><Thread autoFocus={false} showSuggestions={false} showExecutionDetails={false} components={{ Welcome: AgentWelcome }} /></div>
  </div>;
}

function WorkspaceNavigation({ activeKey, onNavigate }: { activeKey: string; onNavigate?: () => void }) {
  const [groupOpen, setGroupOpen] = useState<Record<string, boolean>>({});
  function itemLink(item: typeof workspaceSections[number]) {
    const Icon = item.icon;
    return <Link key={item.key} href={navigationHref(item.key)} onClick={onNavigate} aria-current={item.key === activeKey ? "page" : undefined} className={cn("flex min-h-9 items-center gap-2.5 rounded-md px-3 text-[13px] outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring", item.key === activeKey ? "bg-muted font-medium text-foreground" : "text-muted-foreground hover:bg-muted/70 hover:text-foreground")}><Icon className="size-4 shrink-0" /><span>{item.label}</span></Link>;
  }
  return <nav aria-label="工作台导航" className="space-y-5">
    <div className="space-y-1">{workspaceSections.filter(item => item.key === "overview" || item.key === "projects").map(itemLink)}</div>
    {workspaceGroups.filter(group => group !== "系统").map(group => <Collapsible key={group} open={groupOpen[group] ?? (group === "职业积累" || group === "求职行动" || workspaceSections.some(item => item.key === activeKey && item.group === group))} onOpenChange={open => setGroupOpen(current => ({ ...current, [group]: open }))}>
      <CollapsibleTrigger className="group flex min-h-8 w-full items-center justify-between px-3 text-xs text-muted-foreground outline-none focus-visible:ring-2 focus-visible:ring-ring">{group}<ChevronDown className="size-3.5 transition-transform group-data-[state=closed]:-rotate-90" /></CollapsibleTrigger>
      <CollapsibleContent><div className="mt-1 space-y-0.5">{workspaceSections.filter(item => item.group === group && item.key !== "overview" && item.key !== "projects").map(itemLink)}</div></CollapsibleContent>
    </Collapsible>)}
    {workspaceSections.filter(item => item.group === "系统").map(itemLink)}
  </nav>;
}

function CapabilitySearch({ open, onOpenChange }: { open: boolean; onOpenChange: (value: boolean) => void }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const normalized = query.trim().toLocaleLowerCase();
  const results = workspaceSections.filter(item => (item.label + " " + item.description + " " + item.key + " " + (item.keywords ?? "")).toLocaleLowerCase().includes(normalized));
  return <Dialog open={open} onOpenChange={onOpenChange}>
    <DialogContent className="gap-0 overflow-hidden p-0 sm:max-w-2xl">
      <DialogHeader className="px-5 pb-3 pt-5"><DialogTitle>找到要做的事</DialogTitle><DialogDescription>搜索能力名称；具体目标可以直接交给职业伙伴。</DialogDescription></DialogHeader>
      <div className="flex items-center gap-3 border-y px-5"><Search className="size-4 text-muted-foreground" /><input autoFocus value={query} onChange={event => setQuery(event.target.value)} aria-label="搜索全部能力" placeholder="申请记录、面经、简历、规则…" className="h-12 min-w-0 flex-1 bg-transparent text-sm outline-none" onKeyDown={event => { if (event.key === "Enter" && results.length === 1) { event.preventDefault(); onOpenChange(false); router.push(navigationHref(results[0].key)); } }} /></div>
      <nav aria-label="全部能力" className="max-h-[60dvh] overflow-y-auto p-3">
        {workspaceGroups.map(group => { const items = results.filter(item => item.group === group); return items.length > 0 && <div key={group} className="mb-3"><p className="px-2 py-2 text-xs text-muted-foreground">{group}</p><div className="grid gap-1 sm:grid-cols-2">{items.map(item => { const Icon = item.icon; return <Link id={"capability-" + item.key} key={item.key} href={navigationHref(item.key)} onClick={() => onOpenChange(false)} className="flex items-center gap-3 rounded-lg p-2.5 outline-none hover:bg-muted focus-visible:bg-muted focus-visible:ring-2 focus-visible:ring-ring"><Icon className="size-4 shrink-0 text-muted-foreground" /><div className="min-w-0"><p className="text-sm font-medium">{item.label}</p><p className="mt-0.5 text-xs text-muted-foreground">{item.description}</p></div></Link>; })}</div></div>; })}
        {!results.length && <p role="status" className="p-8 text-center text-sm text-muted-foreground">没有找到匹配的能力。试试公司、面试或材料等关键词。</p>}
      </nav>
    </DialogContent>
  </Dialog>;
}

export function WorkspaceFrame({ children, agentThreadId }: Readonly<{ children: ReactNode; agentThreadId: string }>) {
  return <RuntimeProvider agentThreadId={agentThreadId}><WorkspaceFrameContent>{children}</WorkspaceFrameContent></RuntimeProvider>;
}

function WorkspaceFrameContent({ children }: Readonly<{ children: ReactNode }>) {
  const pathname = usePathname();
  const router = useRouter();
  const runtime = useAui();
  const desktop = useSyncExternalStore(subscribeDesktop, desktopSnapshot, () => false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentMounted, setAgentMounted] = useState(false);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [capabilitiesOpen, setCapabilitiesOpen] = useState(false);
  const [signOutError, setSignOutError] = useState("");
  const activeKey = pathname.split("/").filter(Boolean)[1] ?? "overview";
  const current = workspaceSections.find(item => item.key === activeKey) ?? workspaceSections[0];

  useEffect(() => {
    function handleShortcut(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") { event.preventDefault(); setCapabilitiesOpen(value => !value); }
    }
    window.addEventListener("keydown", handleShortcut);
    return () => window.removeEventListener("keydown", handleShortcut);
  }, []);

  function openAgent(prompt?: string) {
    if (prompt) {
      const existing = runtime.thread.composer().getState().text;
      if (existing.trim() && existing !== prompt && !window.confirm("替换职业伙伴中尚未发送的输入？")) return;
      runtime.thread.composer().setText(prompt);
    }
    setAgentMounted(true);
    setAgentOpen(true);
  }

  async function signOut() {
    if (!window.confirm("确定退出登录？请先保存正在编辑的内容。")) return;
    try {
      const result = await authClient.signOut();
      if (result.error) { setSignOutError("退出失败，请重试。"); return; }
      router.replace("/sign-in");
      router.refresh();
    } catch { setSignOutError("退出失败，请重试。"); }
  }

  return <WorkspaceActionsContext.Provider value={{ openAgent, openCapabilities: () => setCapabilitiesOpen(true) }}>
    <div className="min-h-dvh bg-background lg:grid lg:grid-cols-[13.5rem_minmax(0,1fr)]">
      <a href="#workspace-content" className="sr-only fixed left-4 top-4 z-[60] rounded-md bg-background p-3 focus:not-sr-only">跳到工作内容</a>
      <aside className="sticky top-0 hidden h-dvh flex-col border-r bg-muted/30 lg:flex">
        <div className="px-4 pb-4 pt-6"><Link href="/workspace" className="flex items-center gap-2.5 px-2 text-lg font-semibold tracking-tight"><Bird className="size-5" />CareerAct</Link><button onClick={() => setCapabilitiesOpen(true)} className="mt-6 flex h-9 w-full items-center gap-2 rounded-md border bg-background px-3 text-xs text-muted-foreground outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring"><Search className="size-3.5" />全部能力<kbd className="ml-auto text-[10px]">Ctrl K</kbd></button></div>
        <div className="min-h-0 flex-1 overflow-y-auto px-3 pb-5"><WorkspaceNavigation activeKey={activeKey} /></div>
        <div className="border-t px-5 py-3">{signOutError && <p role="alert" className="mb-2 text-xs text-destructive">{signOutError}</p>}<Button variant="ghost" size="sm" onClick={signOut}><LogOut className="size-3.5" />退出登录</Button></div>
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex h-14 items-center justify-between gap-3 border-b bg-background/95 px-4 backdrop-blur sm:px-6">
          <div className="flex min-w-0 items-center gap-2"><Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setNavigationOpen(true)} aria-label="打开工作台导航"><Menu className="size-4" /></Button><Link href="/workspace/projects" className="hidden items-center gap-2 text-xs text-muted-foreground sm:flex"><FolderKanban className="size-4" />职业工作区</Link><ChevronRight className="hidden size-3 text-muted-foreground sm:block" /><span className="truncate text-sm">{current.label}</span></div>
          <div className="flex shrink-0 gap-1"><Button variant="ghost" size="icon" className="lg:hidden" onClick={() => setCapabilitiesOpen(true)} aria-label="搜索全部能力"><Search className="size-4" /></Button><Button variant="ghost" onClick={() => agentOpen ? setAgentOpen(false) : openAgent()} aria-label={agentOpen ? "收起伙伴" : "职业伙伴"} aria-expanded={agentOpen} aria-controls="career-agent"><PanelRight className="size-4" /><span className="hidden sm:inline">{agentOpen ? "收起伙伴" : "职业伙伴"}</span></Button></div>
        </header>
        <div className={agentOpen && desktop ? "grid grid-cols-[minmax(0,1fr)_20rem] xl:grid-cols-[minmax(0,1fr)_22rem]" : ""}>
          <main id="workspace-content" tabIndex={-1} className="mx-auto w-full min-w-0 max-w-6xl px-5 py-8 outline-none sm:px-8 lg:py-10">{children}</main>
          {desktop && agentMounted && <aside aria-label="职业伙伴工作区" className={agentOpen ? "sticky top-14 h-[calc(100dvh-3.5rem)] min-w-0 border-l" : "hidden"}><AgentDock currentLabel={current.label} onClose={() => setAgentOpen(false)} /></aside>}
        </div>
      </div>
    </div>
    <Dialog open={navigationOpen} onOpenChange={setNavigationOpen}><DialogContent className="left-0 top-0 h-dvh max-w-72 translate-x-0 translate-y-0 overflow-y-auto rounded-none sm:max-w-72"><DialogHeader><DialogTitle>CareerAct</DialogTitle><DialogDescription>项目、职业积累与全部工作能力</DialogDescription></DialogHeader><WorkspaceNavigation activeKey={activeKey} onNavigate={() => setNavigationOpen(false)} />{signOutError && <p role="alert" className="text-xs text-destructive">{signOutError}</p>}<Button variant="ghost" onClick={signOut}><LogOut className="size-4" />退出登录</Button></DialogContent></Dialog>
    <CapabilitySearch open={capabilitiesOpen} onOpenChange={setCapabilitiesOpen} />
    {!desktop && <Dialog open={agentOpen} onOpenChange={setAgentOpen}><DialogContent showCloseButton={false} className="left-auto right-0 top-0 h-dvh max-w-full translate-x-0 translate-y-0 gap-0 rounded-none p-0 sm:max-w-md"><DialogTitle className="sr-only">职业伙伴</DialogTitle><DialogDescription className="sr-only">当前工作面中的对话与反馈</DialogDescription>{agentMounted && <AgentDock currentLabel={current.label} onClose={() => setAgentOpen(false)} />}</DialogContent></Dialog>}
  </WorkspaceActionsContext.Provider>;
}

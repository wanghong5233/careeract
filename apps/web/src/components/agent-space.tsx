"use client";

import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Archive, ArrowUp, BookOpen, ChevronDown, FileText, Folder, Globe, Home, Layers, MoreHorizontal, PanelLeft, PanelRight, Plus, Search, SquarePen, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AccountButton } from "@/components/workspace-account";
import { useWorkspaceActions } from "@/components/workspace-actions";
import { navigationHref, workspaceSections } from "@/components/workspace-sections";
import { beginSpaceConversation, getSpaceStore, removeSpaceProject, type SpaceConversation } from "@/lib/agent-space-state";
import { createProject, deleteProject, ProjectRequestError, readProject, updateProject, type CareerProject } from "@/lib/projects";
import { useProjectList } from "@/hooks/use-project-list";
import { cn } from "@/lib/utils";
import styles from "./agent-space.module.css";

export function AgentHome({ owner, children }: { owner: string; children?: ReactNode }) {
  const { openCapabilities, openAccount, registerAgent, registerContent, registerContentDescription } = useWorkspaceActions();
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentHref = pathname + (searchParams.size ? `?${searchParams}` : "");
  const store = getSpaceStore(owner);
  const updateSpace = store.update;
  const state = useSyncExternalStore(store.subscribe, store.snapshot, store.serverSnapshot);
  const current = state.conversations.find(item => item.id === state.selectedId)!;
  const { projects, updateProjects: setProjects, loading: projectLoading, error: projectError, cursor: projectCursor, refresh: refreshProjects, loadMore: loadMoreProjects } = useProjectList();
  const [mobileNavigation, setMobileNavigation] = useState(false);
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const [showArchived, setShowArchived] = useState(false);
  const [contextOpen, setContextOpen] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [edit, setEdit] = useState<{ kind: "conversation" | "project" | "create"; id?: string; title: string } | null>(null);
  const [editingError, setEditingError] = useState("");
  const [busy, setBusy] = useState(false);
  const [leaveAction, setLeaveAction] = useState<(() => void) | null>(null);
  const [deleting, setDeleting] = useState<CareerProject | null>(null);
  const [deleteError, setDeleteError] = useState("");
  const [deleteNeedsCheck, setDeleteNeedsCheck] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const pendingNavigation = useRef<string | null>(null);
  const space = useRef<HTMLDivElement>(null);
  const project = projects.find(item => item.id === current.projectId);
  const projectLabel = project?.title ?? (current.projectId ? "项目暂不可用" : "个人空间");
  const activeSection = workspaceSections.find(item => navigationHref(item.key) === pathname);
  const routeProject = projects.find(item => pathname === `/workspace/projects/${item.id}`);
  const tabLabel = routeProject?.title ?? activeSection?.label ?? "职业项目";
  const tabs = current.tabs;
  const routeOpen = pathname !== "/workspace";
  const visibleTabs = routeOpen && !tabs.some(tab => tab.href === currentHref)
    ? [...tabs, { href: currentHref, label: tabLabel }] : tabs;
  const panelOpen = contextOpen || (routeOpen && !current.panelHidden);

  useEffect(() => {
    if (pendingNavigation.current && pendingNavigation.current !== currentHref) return;
    pendingNavigation.current = null;
    store.update(previous => {
      const selected = previous.conversations.find(item => item.id === previous.selectedId)!;
      const existing = selected.tabs.find(tab => tab.href === currentHref);
      const renamedProject = routeProject && existing && existing.label !== tabLabel;
      if (selected.activeHref === currentHref && (!routeOpen || existing) && !renamedProject) return previous;
      return { ...previous, conversations: previous.conversations.map(item => item.id === previous.selectedId ? {
        ...item, activeHref: currentHref,
        tabs: routeOpen && !existing ? [...item.tabs, { href: currentHref, label: tabLabel }] : renamedProject ? item.tabs.map(tab => tab.href === currentHref ? { ...tab, label: tabLabel } : tab) : item.tabs,
      } : item) };
    });
  }, [currentHref, routeOpen, routeProject, tabLabel, state.selectedId, store]);

  useEffect(() => registerContentDescription(content => {
    store.update(previous => {
      const selected = previous.conversations.find(item => item.id === previous.selectedId)!;
      if (content.href !== currentHref || selected.tabs.find(tab => tab.href === content.href)?.label === content.label) return previous;
      return { ...previous, conversations: previous.conversations.map(item => item.id === previous.selectedId ? {
        ...item, tabs: item.tabs.some(tab => tab.href === content.href)
          ? item.tabs.map(tab => tab.href === content.href ? content : tab) : [...item.tabs, content],
      } : item) };
    });
  }), [currentHref, registerContentDescription, store]);

  useEffect(() => registerAgent(prompt => {
    setContextOpen(false);
    store.update(previous => ({ ...previous, conversations: previous.conversations.map(item => item.id === previous.selectedId ? { ...item, panelHidden: window.matchMedia("(max-width: 900px)").matches, draft: prompt && !item.archived ? (item.draft ? item.draft + "\n\n" + prompt : prompt) : item.draft } : item) }));
    if (store.snapshot().conversations.find(item => item.id === store.snapshot().selectedId)?.archived) setFeedback("请先恢复这段对话，再继续工作。");
    requestAnimationFrame(() => input.current?.focus());
  }), [registerAgent, store]);

  function update(patch: Partial<SpaceConversation>) {
    setFeedback("");
    store.update(previous => ({ ...previous, conversations: previous.conversations.map(item => item.id === previous.selectedId ? { ...item, ...patch } : item) }));
  }

  function start(projectId: string | null = null, guarded = false) {
    if (!guarded && !window.dispatchEvent(new Event("careeract:before-navigate", { cancelable: true }))) {
      setMobileNavigation(false);
      setLeaveAction(() => () => start(projectId, true));
      return;
    }
    pendingNavigation.current = "/workspace";
    store.update(previous => beginSpaceConversation(previous, crypto.randomUUID(), projectId));
    router.push("/workspace");
    if (projectId) setCollapsed(previous => previous.filter(id => id !== projectId));
    setContextOpen(false); setShowArchived(false); setMobileNavigation(false); setFeedback(""); requestAnimationFrame(() => input.current?.focus());
  }

  function select(id: string, guarded = false) {
    if (!guarded && id !== current.id && !window.dispatchEvent(new Event("careeract:before-navigate", { cancelable: true }))) {
      setMobileNavigation(false);
      setLeaveAction(() => () => select(id, true));
      return;
    }
    const selected = state.conversations.find(item => item.id === id)!;
    pendingNavigation.current = selected.activeHref;
    store.update(previous => ({ ...previous, selectedId: id }));
    router.push(selected.activeHref);
    setContextOpen(false); setMobileNavigation(false); setFeedback("");
  }

  function openRoute(href: string, guarded = false) {
    if (href !== currentHref && !guarded && !window.dispatchEvent(new Event("careeract:before-navigate", { cancelable: true }))) {
      setMobileNavigation(false);
      setLeaveAction(() => () => openRoute(href, true));
      return;
    }
    updateSpace(previous => ({ ...previous, conversations: previous.conversations.map(item => item.id === previous.selectedId ? { ...item, panelHidden: false } : item) }));
    setContextOpen(false); setMobileNavigation(false); router.push(href);
  }

  useEffect(() => registerContent(openRoute));

  function closeTab(href: string, guarded = false) {
    if (currentHref === href && !guarded && !window.dispatchEvent(new Event("careeract:before-navigate", { cancelable: true }))) {
      setMobileNavigation(false);
      setLeaveAction(() => () => closeTab(href, true));
      return;
    }
    const remaining = visibleTabs.filter(tab => tab.href !== href);
    const destination = remaining.at(-1)?.href ?? "/workspace";
    if (currentHref === href) pendingNavigation.current = destination;
    store.update(previous => ({ ...previous, conversations: previous.conversations.map(item => item.id === previous.selectedId ? { ...item, tabs: remaining, activeHref: currentHref === href ? destination : item.activeHref } : item) }));
    if (currentHref === href) router.push(destination);
  }

  async function saveEdit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!edit || !edit.title.trim() || busy) return;
    setBusy(true); setEditingError("");
    try {
      if (edit.kind === "conversation") {
        store.update(previous => ({ ...previous, conversations: previous.conversations.map(item => item.id === edit.id ? { ...item, title: edit.title.trim() } : item) }));
      } else {
        const existing = projects.find(item => item.id === edit.id);
        const saved = edit.kind === "create"
          ? await createProject({ id: edit.id!, title: edit.title.trim(), purpose: "" })
          : await updateProject(existing!.id, { title: edit.title.trim(), purpose: existing!.purpose, status: existing!.status, version: existing!.version });
        setProjects(previous => [saved, ...previous.filter(item => item.id !== saved.id)]);
        window.dispatchEvent(new Event("careeract:projects-changed"));
      }
      setEdit(null);
    } catch (error) { setEditingError(error instanceof Error ? error.message : "保存失败，输入已保留。"); }
    finally { setBusy(false); }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (current.archived) return;
    if (current.draft.trim()) setFeedback("此对话的 Agent 连接尚未开放。内容已保留为草稿，未发送。");
  }

  function requestDelete(item: CareerProject, guarded = false) {
    setMobileNavigation(false);
    if (!guarded && !window.dispatchEvent(new Event("careeract:before-navigate", { cancelable: true }))) {
      setLeaveAction(() => () => requestDelete(item, true));
      return;
    }
    setDeleteError(""); setDeleteNeedsCheck(false); setDeleting(item);
  }

  function finishDelete(id: string) {
    const destination = pathname === `/workspace/projects/${id}` ? "/workspace" : currentHref;
    if (destination !== currentHref) pendingNavigation.current = destination;
    store.update(previous => removeSpaceProject(previous, id));
    setProjects(previous => previous.filter(item => item.id !== id));
    setCollapsed(previous => previous.filter(item => item !== id));
    setDeleting(null); setContextOpen(false); setFeedback("项目已删除。对话与材料保留，项目规则已停用。");
    window.dispatchEvent(new Event("careeract:projects-changed"));
    if (destination !== currentHref) router.push(destination);
  }

  async function confirmDelete() {
    if (!deleting || deleteBusy || deleteNeedsCheck) return;
    setDeleteBusy(true); setDeleteError("");
    try {
      await deleteProject(deleting.id, deleting.version);
      finishDelete(deleting.id);
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : "尚不能确认删除结果，请重新读取核对。");
      setDeleteNeedsCheck(true);
    } finally { setDeleteBusy(false); }
  }

  async function checkDelete() {
    if (!deleting || deleteBusy) return;
    setDeleteBusy(true);
    try {
      const latest = await readProject(deleting.id, AbortSignal.timeout(20_000));
      setDeleting(latest); setDeleteNeedsCheck(false); setDeleteError("");
    } catch (error) {
      if (error instanceof ProjectRequestError && error.status === 404) finishDelete(deleting.id);
      else setDeleteError(error instanceof Error ? error.message : "无法核对项目，请重试。");
    } finally { setDeleteBusy(false); }
  }

  const listedConversations = state.conversations.filter(item => item.archived === showArchived && (item.draft || item.title !== "新对话" || item.archived));

  useEffect(() => {
    function dismissMenus(event: PointerEvent | KeyboardEvent) {
      document.querySelectorAll<HTMLDetailsElement>(`details.${styles.conversationMenu}[open]`).forEach(menu => {
        if (event instanceof KeyboardEvent ? event.key === "Escape" : event.target instanceof Node && !menu.contains(event.target)) {
          menu.open = false;
          if (event instanceof KeyboardEvent) menu.querySelector<HTMLElement>("summary")?.focus();
        }
      });
    }
    document.addEventListener("pointerdown", dismissMenus);
    document.addEventListener("keydown", dismissMenus);
    return () => { document.removeEventListener("pointerdown", dismissMenus); document.removeEventListener("keydown", dismissMenus); };
  }, []);

  const navigation = (
    <nav className={styles.navigation} aria-label="职业项目与对话">
      <div className="flex items-center justify-between px-2 pb-5 pt-1"><span className="text-sm font-semibold tracking-tight">CareerAct</span><Button variant="ghost" size="icon" className="md:hidden" aria-label="关闭项目导航" onClick={() => setMobileNavigation(false)}><X /></Button></div>
      <button className={styles.navButton} onClick={() => start()}><SquarePen />新对话</button>
      <button className={cn(styles.navButton, pathname === "/workspace/background" && panelOpen && !contextOpen && styles.selected)} aria-current={pathname === "/workspace/background" && panelOpen && !contextOpen ? "page" : undefined} onClick={() => openRoute("/workspace/background")}><BookOpen />职业背景</button>
      <div className={styles.sectionHeading}><span>项目</span><Button variant="ghost" size="icon" title="新建项目" aria-label="新建项目" onClick={() => { setMobileNavigation(false); setEditingError(""); setEdit({ kind: "create", id: crypto.randomUUID(), title: "" }); }}><Plus className="size-3.5" /></Button></div>
      {projectLoading && <p role="status" className="px-2 py-3 text-xs text-muted-foreground">正在读取项目…</p>}
      {projectError && <div className="px-2 py-3 text-xs"><p role="alert" className="leading-5 text-destructive">{projectError}</p><Button variant="ghost" size="sm" onClick={refreshProjects}>重新读取</Button></div>}
      {!projectLoading && !projectError && !projects.length && <p className="px-2 py-2 text-xs leading-6 text-muted-foreground">还没有项目。可以先对话，再按职业目标组织。</p>}
      {projects.map(item => <section key={item.id} className="mb-2">
        <div className="relative flex items-center">
          <button className={cn(styles.navButton, "min-w-0 flex-1")} aria-expanded={!collapsed.includes(item.id)} onClick={() => setCollapsed(previous => previous.includes(item.id) ? previous.filter(id => id !== item.id) : [...previous, item.id])}>
            <Folder /><span className="truncate" title={item.title}>{item.title}</span><ChevronDown className={cn("ml-auto !size-3", collapsed.includes(item.id) && "-rotate-90")} />
          </button>
          <Button variant="ghost" size="icon" className="size-7 shrink-0" title="新对话" aria-label={`在${item.title}中新建对话`} onClick={() => start(item.id)}><Plus className="size-3.5" /></Button>
          <details className={styles.conversationMenu}>
            <summary aria-label={`${item.title}的项目操作`} title="项目操作"><MoreHorizontal className="size-3.5" /></summary>
            <div>
              <button onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); openRoute(`/workspace/projects/${item.id}`); }}>项目详情</button>
              <button onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); setMobileNavigation(false); setEditingError(""); setEdit({ kind: "project", id: item.id, title: item.title }); }}>重命名</button>
              <button className="text-destructive" onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); requestDelete(item); }}>删除项目</button>
            </div>
          </details>
        </div>
        {!collapsed.includes(item.id) && listedConversations.filter(conversation => conversation.projectId === item.id).map(renderConversation)}
      </section>)}
      {projectCursor && <Button variant="ghost" size="sm" disabled={projectLoading} onClick={loadMoreProjects}>更多项目</Button>}
      <div className={styles.sectionHeading}><span>{showArchived ? "已归档对话" : "对话"}</span><Button variant="ghost" size="icon" title={showArchived ? "显示对话" : "已归档对话"} aria-label={showArchived ? "显示对话" : "已归档对话"} aria-pressed={showArchived} onClick={() => setShowArchived(value => !value)}><Archive className="size-3.5" /></Button></div>
      {listedConversations.filter(item => !item.projectId || !projects.some(project => project.id === item.projectId)).map(renderConversation)}
      {showArchived && !listedConversations.length && <p className="px-2 text-xs text-muted-foreground">没有已归档对话。</p>}
    </nav>
  );

  return <div className={cn(styles.shell, !state.navigation && styles.noNavigation)}>
    <a href="#career-agent-input" className={styles.skipLink}>跳到对话输入</a>
    <aside className={styles.rail} aria-label="空间导航">
      <span className={styles.wordmark} aria-hidden="true">CA</span>
      <Button variant="ghost" size="icon" title="项目与对话" aria-label="展开或收起项目" aria-expanded={state.navigation} className="hidden md:inline-flex" onClick={() => store.update(previous => ({ ...previous, navigation: !previous.navigation }))}><PanelLeft /></Button>
      <Button variant="ghost" size="icon" title="项目与对话" aria-label="打开项目导航" aria-expanded={mobileNavigation} className="md:hidden" onClick={() => setMobileNavigation(value => !value)}><PanelLeft /></Button>
      <Button variant="ghost" size="icon" title="回到 Agent" aria-label="回到 Agent" onClick={() => { openRoute("/workspace"); input.current?.focus(); }}><Home /></Button>
      <Button variant="ghost" size="icon" title="职业能力 · Ctrl/⌘ K" aria-label="探索职业能力" onClick={openCapabilities}><Search /></Button>
      <Button variant="ghost" size="icon" title="资料与成果" aria-label="资料与成果" onClick={() => openRoute("/workspace/library")}><FileText /></Button>
      <div className="mt-auto"><AccountButton compact onClick={openAccount} /></div>
    </aside>
    {navigation}
    <Dialog open={mobileNavigation} onOpenChange={setMobileNavigation}><DialogContent showCloseButton={false} className={styles.mobileDrawer} style={{ translate: "0 0" }}><DialogTitle className="sr-only">项目与对话</DialogTitle><DialogDescription className="sr-only">选择、创建或继续工作</DialogDescription>{navigation}</DialogContent></Dialog>
    <div ref={space} className={cn(styles.space, panelOpen && styles.withPanel)} style={{ "--panel-width": `${state.panelWidth}%` } as CSSProperties}>
      <main className={styles.agent}>
        <header className={styles.header}><span className="min-w-0 flex-1 truncate text-sm" title={current.title}>{project && <span className="text-muted-foreground">{project.title} / </span>}{current.title}</span><Button size="icon" variant="ghost" title="本次上下文" aria-label="查看本次上下文" aria-pressed={contextOpen} onClick={() => setContextOpen(value => !value)}><Layers /></Button><Button size="icon" variant="ghost" title={panelOpen ? "收起内容区" : "展开内容区"} aria-label={panelOpen ? "收起内容区" : "展开内容区"} onClick={() => { if (contextOpen) setContextOpen(false); else if (routeOpen) update({ panelHidden: !current.panelHidden }); else if (current.tabs.length) openRoute(current.tabs.at(-1)!.href); else setContextOpen(true); }}><PanelRight /></Button></header>
        <div className={styles.startArea}><div className={styles.welcome}><p className={styles.kicker}>你的个人职业 Agent</p><h1>想把哪件事往前推进？</h1><p className={styles.introduction}>告诉我目标、想法或需要调整的内容。</p></div>
          <div className={styles.composerArea}><form onSubmit={submit} className={styles.composer}><label htmlFor="career-agent-input" className="sr-only">交代目标或反馈</label><textarea id="career-agent-input" ref={input} rows={3} maxLength={4000} readOnly={current.archived} value={current.draft} onChange={event => update({ draft: event.target.value })} onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="从你的下一步开始…" /><div className="flex items-center justify-between gap-3"><label className={styles.projectSelector}><Folder className="size-3.5" /><span className="sr-only">对话所属项目</span><select disabled={current.archived} aria-label="对话所属项目" value={current.projectId ?? ""} onChange={event => update({ projectId: event.target.value || null })}><option value="">个人空间</option>{current.projectId && !project && <option value={current.projectId} disabled>项目暂不可用</option>}{projects.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label><Button type="submit" size="icon" disabled={!current.draft.trim() || current.archived} title="发送 · Ctrl/⌘ Enter" aria-label="发送" className="size-8 rounded-full"><ArrowUp /></Button></div></form>
          {feedback && <p role="status" className={styles.feedback}>{feedback}</p>}
          {!store.storageAvailable() && <p role="alert" className={styles.feedback}>此浏览器无法保留草稿，请勿关闭页面。</p>}
          {current.archived && <p className={styles.feedback}>已归档。<button className="underline underline-offset-4" onClick={() => update({ archived: false })}>恢复对话</button></p>}
          <button className={styles.discover} onClick={openCapabilities}>探索职业能力<span>机会 · 材料 · 申请 · 准备</span></button>
          </div>
        </div>
      </main>
      {(routeOpen || contextOpen) && <>{panelOpen && <div role="separator" aria-label="调整内容区宽度" aria-orientation="vertical" tabIndex={0} aria-valuemin={30} aria-valuemax={65} aria-valuenow={state.panelWidth} className={styles.resizeHandle} onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); store.update(previous => ({ ...previous, panelWidth: Math.min(65, Math.max(30, previous.panelWidth + (event.key === "ArrowLeft" ? 2 : -2))) })); } }} onPointerDown={event => event.currentTarget.setPointerCapture(event.pointerId)} onPointerMove={event => { if (!event.currentTarget.hasPointerCapture(event.pointerId)) return; const bounds = space.current?.getBoundingClientRect(); if (bounds) store.update(previous => ({ ...previous, panelWidth: Math.min(65, Math.max(30, (bounds.right - event.clientX) / bounds.width * 100)) })); }} onPointerUp={event => event.currentTarget.releasePointerCapture(event.pointerId)} />}
      <aside className={cn(styles.content, !panelOpen && styles.hiddenContent)} aria-label="内容工作区"><div className={styles.tabBar}><div role="tablist" aria-label="打开的内容" className={styles.tabList} onKeyDown={event => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return; const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')); const selected = buttons.indexOf(document.activeElement as HTMLButtonElement); if (selected < 0) return; event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (selected + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length; buttons[next]?.focus(); buttons[next]?.click(); }}>{visibleTabs.map(tab => <div key={tab.href} className={cn(styles.tab, !contextOpen && tab.href === currentHref && styles.activeTab)}><button role="tab" tabIndex={!contextOpen && tab.href === currentHref ? 0 : -1} aria-selected={!contextOpen && tab.href === currentHref} aria-controls="space-content" id={`tab-${tab.href}`} title={tab.label} onClick={() => openRoute(tab.href)}><FileText className="size-3.5" /><span className="truncate">{tab.label}</span></button><button title={`关闭${tab.label}`} aria-label={`关闭${tab.label}标签`} onClick={() => closeTab(tab.href)}><X className="size-3" /></button></div>)}{contextOpen && <div className={cn(styles.tab, styles.activeTab)}><button role="tab" aria-selected aria-controls="space-content" id="tab-context"><Layers className="size-3.5" />本次上下文</button><button aria-label="关闭上下文标签" onClick={() => setContextOpen(false)}><X className="size-3" /></button></div>}</div><Button variant="ghost" size="icon" title="收起并保留内容" aria-label="收起内容区并保留标签" onClick={() => { setContextOpen(false); update({ panelHidden: true }); requestAnimationFrame(() => input.current?.focus()); }}><PanelRight /></Button></div>
        <div id="space-content" role="tabpanel" aria-labelledby={contextOpen ? "tab-context" : `tab-${currentHref}`} className={styles.surface}>{contextOpen && <article className={styles.document}><p className={styles.kicker}>本次上下文</p><h2>{projectLabel}</h2><p>选择项目决定这项工作的范围。个人职业背景可以按需复用，另一项目的外部执行授权不会自动继承。</p><section><h3>职业背景</h3><p>查看并维护已确认的个人资料。</p><Button variant="outline" size="sm" onClick={() => openRoute("/workspace/background")}>打开职业背景</Button></section><section><h3>当前项目</h3><p>{project?.purpose || "尚未填写项目目标。你可以先在对话中整理想法。"}</p>{project && <Button variant="outline" size="sm" onClick={() => openRoute(`/workspace/projects/${project.id}`)}>打开项目详情</Button>}</section><section><h3>材料与规则</h3><div className="flex flex-wrap gap-2"><Button variant="outline" size="sm" onClick={() => openRoute("/workspace/library")}>资料与成果</Button><Button variant="outline" size="sm" onClick={() => openRoute("/workspace/assistant")}>规则与笔记</Button></div><p className="mt-4">此处用于选择工作范围；当前对话尚未记录 Agent 实际读取的材料。</p></section><section><h3 className="flex items-center gap-2"><Globe className="size-4" />浏览器</h3><p>当前没有关联的浏览器执行会话。</p></section></article>}<div className={cn(styles.routeContent, contextOpen && styles.hiddenContent)}>{children}</div></div>
      </aside></>}
    </div>
    <Dialog open={!!deleting} onOpenChange={value => { if (!value && !deleteBusy) setDeleting(null); }}>
      <DialogContent>
        <DialogHeader><DialogTitle>删除项目？</DialogTitle><DialogDescription>将永久删除“{deleting?.title}”。对话与材料会保留在个人空间，项目规则与笔记会停用，已保存的职业背景不受影响。此操作无法撤销。</DialogDescription></DialogHeader>
        {deleteError && <p role="alert" className="text-sm text-destructive">{deleteError}</p>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" disabled={deleteBusy} onClick={() => setDeleting(null)}>取消</Button>
          {deleteNeedsCheck ? <Button disabled={deleteBusy} onClick={checkDelete}>{deleteBusy ? "正在核对…" : "重新读取并核对"}</Button> : <Button variant="destructive" disabled={deleteBusy} onClick={confirmDelete}>{deleteBusy ? "正在删除…" : "删除项目"}</Button>}
        </div>
      </DialogContent>
    </Dialog>
    <Dialog open={!!leaveAction} onOpenChange={value => { if (!value) setLeaveAction(null); }}>
      <DialogContent>
        <DialogHeader><DialogTitle>有未保存的修改</DialogTitle><DialogDescription>切换会放弃内容区当前未保存的输入。对话草稿和已保存的资料仍会保留。</DialogDescription></DialogHeader>
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={() => setLeaveAction(null)}>继续编辑</Button>
          <Button onClick={() => { const action = leaveAction; setLeaveAction(null); action?.(); }}>放弃修改并切换</Button>
        </div>
      </DialogContent>
    </Dialog>
    <Dialog open={!!edit} onOpenChange={value => { if (!value && !busy) setEdit(null); }}><DialogContent><DialogHeader><DialogTitle>{edit?.kind === "create" ? "新建项目" : "重命名"}</DialogTitle><DialogDescription>{edit?.kind === "conversation" ? "方便下次找到这项工作。" : "按你的职业目标组织工作，目标可以稍后补充。"}</DialogDescription></DialogHeader><form onSubmit={saveEdit} className="space-y-4"><label htmlFor="space-name" className="block text-sm">名称</label><input id="space-name" autoFocus required maxLength={120} value={edit?.title ?? ""} disabled={busy} onChange={event => setEdit(previous => previous ? { ...previous, title: event.target.value } : null)} className="h-10 w-full rounded-md border bg-background px-3 text-sm" />{editingError && <p role="alert" className="text-sm text-destructive">{editingError}</p>}<div className="flex justify-end gap-2"><Button type="button" variant="ghost" disabled={busy} onClick={() => setEdit(null)}>取消</Button><Button type="submit" disabled={busy || !edit?.title.trim()}>{busy ? "正在保存…" : "保存"}</Button></div></form></DialogContent></Dialog>
  </div>;

  function renderConversation(item: SpaceConversation) {
    return <div key={item.id} className={cn(styles.conversationRow, item.id === state.selectedId && styles.selected)}><button aria-current={item.id === state.selectedId ? "page" : undefined} onClick={() => select(item.id)} className={styles.conversationLink} title={item.title}><span className="truncate">{item.title}</span>{item.draft && <span className={styles.draftMark}>草稿</span>}</button><details className={styles.conversationMenu}><summary aria-label={`${item.title}的操作`} title="对话操作"><MoreHorizontal className="size-3.5" /></summary><div><button onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); setMobileNavigation(false); setEditingError(""); setEdit({ kind: "conversation", id: item.id, title: item.title }); }}>重命名</button><button onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); store.update(previous => ({ ...previous, conversations: previous.conversations.map(conversation => conversation.id === item.id ? { ...conversation, archived: !conversation.archived } : conversation) })); }}>{item.archived ? "恢复对话" : "归档对话"}</button></div></details></div>;
  }
}

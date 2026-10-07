"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type FormEvent, type ReactNode } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Archive, ArchiveRestore, ArrowUp, BookOpen, ChevronDown, FileText, Folder, ListTree, MessageSquare, MessageSquarePlus, MoreHorizontal, PanelLeft, PanelRight, Pin, PinOff, Plus, RotateCcw, Search, Square, SquarePen, Trash2, X } from "lucide-react";
import { useAui, useAuiState } from "@assistant-ui/react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { AccountButton } from "@/components/workspace-account";
import { AgentComposerTools } from "@/components/agent-composer-tools";
import { AgentProjectPicker } from "@/components/agent-project-picker";
import { ConversationHistory } from "@/components/conversation-history";
import { SideChatPanel, useSideChat } from "@/components/side-chat";
import { TooltipIconButton } from "@/components/tooltip-icon-button";
import { useWorkspaceActions } from "@/components/workspace-actions";
import { navigationHref, workspaceSections } from "@/components/workspace-sections";
import { beginSpaceConversation, getSpaceStore, removeSpaceProject, type SpaceConversation } from "@/lib/agent-space-state";
import { createProject, deleteProject, ProjectRequestError, readProject, updateProject, type CareerProject } from "@/lib/projects";
import { useProjectList } from "@/hooks/use-project-list";
import { useAgentConversations } from "@/hooks/use-agent-conversations";
import { useConversationHistory } from "@/hooks/use-conversation-history";
import { cn } from "@/lib/utils";
import { cancelConversationRun, reconcileConversationRun, queueConversationSend, takeConversationSend } from "@/lib/agent-runtime";
import { ConversationRequestError, createConversationBranch, generateConversationTitle, readConversation } from "@/lib/agent-conversations";
import { deleteConversationSelection, selectConversationRange } from "@/lib/conversation-selection";
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
  const conversations = useAgentConversations(owner);
  const history = useConversationHistory(current.id, !!current.version);
  const mainCheckpoint = history.history?.messages.findLast(message => message.run_status === "COMPLETED")?.id ?? null;
  const sideChat = useSideChat(owner, current.id, !!current.version, mainCheckpoint);
  const sideOpen = !current.archived && !!sideChat.state.chat && !sideChat.state.hidden;
  const aui = useAui();
  const localRunning = useAuiState(runtime => runtime.thread.isRunning);
  const runtimeRunning = localRunning || !!history.activeRun;
  const runtimeMessages = useAuiState(runtime => runtime.thread.messages);
  const runtimeHasMessages = runtimeMessages.length > 0;
  const [conversationBusy, setConversationBusy] = useState(false);
  const [messageEdit, setMessageEdit] = useState<{ conversationId: string; id: string; text: string } | null>(null);
  const activeMessageEdit = !current.archived && messageEdit?.conversationId === current.id ? messageEdit : null;
  const branchRequest = useRef<{ key: string; id: string } | null>(null);
  const branchLock = useRef(false);
  const [sendBusy, setSendBusy] = useState(false);
  const [stopBusy, setStopBusy] = useState(false);
  const { projects, updateProjects: setProjects, loading: projectLoading, error: projectError, cursor: projectCursor, refresh: refreshProjects, loadMore: loadMoreProjects } = useProjectList();
  const [mobileNavigation, setMobileNavigation] = useState(false);
  const [collapsed, setCollapsed] = useState<string[]>([]);
  const recentExpanded = state.recentExpanded ?? true;
  const archiveExpanded = state.archiveExpanded ?? false;
  const setRecentExpanded = (open: boolean) => store.update(previous => ({ ...previous, recentExpanded: open }));
  const setArchiveExpanded = (open: boolean) => store.update(previous => ({ ...previous, archiveExpanded: open }));
  const [deletingConversations, setDeletingConversations] = useState<SpaceConversation[]>([]);
  const [selectedConversations, setSelectedConversations] = useState<string[]>([]);
  const [selectingConversations, setSelectingConversations] = useState(false);
  const selectionAnchor = useRef<string | null>(null);
  const conversationClick = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [conversationDeleteError, setConversationDeleteError] = useState("");
  const [conversationDeleteCheck, setConversationDeleteCheck] = useState(false);
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
  const expandNavigation = useRef<HTMLButtonElement>(null);
  const collapseNavigation = useRef<HTMLButtonElement>(null);
  const pendingNavigation = useRef<string | null>(null);
  const sendingConversation = useRef<string | null>(null);
  const stopRequested = useRef(false);
  const wasRunning = useRef(false);
  const space = useRef<HTMLDivElement>(null);
  const project = projects.find(item => item.id === current.projectId);
  const projectLabel = project?.title ?? (current.projectId ? "项目暂不可用" : "个人 Agent");
  const activeSection = workspaceSections.find(item => navigationHref(item.key) === pathname);
  const routeProject = projects.find(item => pathname === `/projects/${item.id}` || pathname === `/workspace/projects/${item.id}`);
  const tabLabel = routeProject?.title ?? activeSection?.label ?? "职业项目";
  const tabs = current.tabs;
  const routeOpen = pathname !== "/" && pathname !== "/workspace";
  const visibleTabs = routeOpen && !tabs.some(tab => tab.href === currentHref)
    ? [...tabs, { href: currentHref, label: tabLabel }] : tabs;
  const panelOpen = sideOpen || contextOpen || (routeOpen && !current.panelHidden);

  useEffect(() => () => { if (conversationClick.current) clearTimeout(conversationClick.current); }, []);

  useEffect(() => {
    const replace = (event: Event) => {
      const detail = (event as CustomEvent<{ sourceId: string; messageId?: string; quote?: string }>).detail;
      const selected = store.snapshot().conversations.find(item => item.id === detail.sourceId);
      if (!selected?.archived && detail.sourceId === current.id) void sideChat.open(detail.messageId, detail.quote);
    };
    window.addEventListener("careeract:side-replace", replace);
    return () => window.removeEventListener("careeract:side-replace", replace);
  }, [current.id, store, sideChat]);

  useEffect(() => {
    if (wasRunning.current && !localRunning) void history.refresh();
    wasRunning.current = localRunning;
  }, [localRunning, history]);

  const sendText = useCallback(async (text: string, id: string) => {
    if (sendingConversation.current === id) return;
    sendingConversation.current = id;
    stopRequested.current = false;
    setSendBusy(true);
    setFeedback("");
    try {
      await Promise.resolve(aui.thread.append({ role: "user", content: [{ type: "text", text }] }));
      if (!stopRequested.current && store.snapshot().selectedId === id) {
        store.update(previous => ({ ...previous, conversations: previous.conversations.map(item => item.id === id && item.draft.trim() === text ? { ...item, draft: "" } : item) }));
      }
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "本次发送未确认，草稿仍保留，请核对后重试。");
    } finally {
      if (sendingConversation.current === id) sendingConversation.current = null;
      setSendBusy(false);
    }
  }, [aui, store]);

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

  useEffect(() => {
    const sendPending = () => {
      if (store.snapshot().conversations.find(item => item.id === current.id)?.archived || !current.version || history.loading || history.error || history.activeRun) return;
      const text = takeConversationSend(owner, current.id);
      if (text) void sendText(text, current.id);
    };
    sendPending();
    window.addEventListener("careeract:send-ready", sendPending);
    return () => window.removeEventListener("careeract:send-ready", sendPending);
  }, [current.id, current.version, history.loading, history.error, history.activeRun, owner, store, sendText]);

  function update(patch: Partial<SpaceConversation>) {
    setFeedback("");
    store.update(previous => ({ ...previous, conversations: previous.conversations.map(item => item.id === previous.selectedId ? { ...item, ...patch } : item) }));
  }

  function toggleNavigation() {
    store.update(previous => ({ ...previous, navigation: !previous.navigation }));
    requestAnimationFrame(() => (store.snapshot().navigation ? collapseNavigation : expandNavigation).current?.focus());
  }

  function hideContent() {
    if (sideOpen) sideChat.store.update(previous => ({ ...previous, hidden: true }));
    setContextOpen(false);
    update({ panelHidden: true });
    requestAnimationFrame(() => input.current?.focus());
  }

  function showCapabilities() {
    setMobileNavigation(false);
    openCapabilities();
  }

  async function start(projectId: string | null = null, guarded = false) {
    if (conversationBusy) return;
    if (runtimeRunning || sendBusy) {
      setFeedback("请先停止当前运行，再切换到新对话。");
      return;
    }
    if (!guarded && !window.dispatchEvent(new Event("careeract:before-navigate", { cancelable: true }))) {
      setMobileNavigation(false);
      setLeaveAction(() => () => start(projectId, true));
      return;
    }
    pendingNavigation.current = "/";
    store.update(previous => beginSpaceConversation(previous, crypto.randomUUID(), projectId));
    const id = store.snapshot().selectedId;
    router.push("/");
    if (projectId) setCollapsed(previous => previous.filter(id => id !== projectId));
    setContextOpen(false); setRecentExpanded(true); setMobileNavigation(false); setFeedback(""); requestAnimationFrame(() => input.current?.focus());
    setConversationBusy(true);
    try { await conversations.persist(id); }
    catch (error) { setFeedback(error instanceof Error ? error.message : "未能确认创建结果，草稿仍保留。请重新读取核对。"); }
    finally { setConversationBusy(false); }
  }

  async function changeConversation(id: string, changes: { project_id?: string | null; archived?: boolean; model_id?: string; pinned?: boolean }, guarded = false) {
    if (conversationClick.current) clearTimeout(conversationClick.current);
    if (conversationBusy || sendBusy) return;
    if (changes.archived && id === current.id && !guarded && !window.dispatchEvent(new Event("careeract:before-navigate", { cancelable: true }))) {
      setLeaveAction(() => () => void changeConversation(id, changes, true));
      return;
    }
    setConversationBusy(true); setFeedback("");
    try {
      await conversations.persist(id, changes);
      if (changes.archived !== undefined) {
        if (changes.archived && store.snapshot().selectedId === id) {
          store.update(previous => beginSpaceConversation(previous, crypto.randomUUID()));
          pendingNavigation.current = "/"; router.push("/"); setContextOpen(false);
        }
        if (!changes.archived) setRecentExpanded(true);
        setFeedback(changes.archived ? "对话已归档，可在侧栏归档列表中恢复。" : "对话已恢复。");
        void history.refresh();
      }
    }
    catch (error) { setFeedback(error instanceof Error ? error.message : "未能保存对话，请重新读取核对。"); }
    finally { setConversationBusy(false); }
  }

  async function confirmConversationDelete() {
    if (!deletingConversations.length || conversationBusy || conversationDeleteCheck) return;
    setConversationBusy(true); setConversationDeleteError("");
    const result = await deleteConversationSelection(deletingConversations, conversations.remove);
    if (store.snapshot().selectedId !== state.selectedId) { pendingNavigation.current = "/"; router.push("/"); }
    setDeletingConversations(result.remaining);
    setSelectedConversations(previous => previous.filter(id => result.remaining.some(item => item.id === id)));
    if (result.error) {
      setConversationDeleteError(`已删除 ${result.deleted} 段；其余未继续删除。${result.error instanceof Error ? result.error.message : "删除结果未确认，请先重新读取核对。"}`);
      setConversationDeleteCheck(true);
    } else { setSelectingConversations(false); setFeedback(`已删除 ${result.deleted} 段对话。`); }
    setConversationBusy(false);
  }

  async function checkConversationDelete() {
    const deletingConversation = deletingConversations[0];
    if (!deletingConversation || conversationBusy) return;
    setConversationBusy(true);
    try {
      const saved = await readConversation(deletingConversation.id);
      conversations.accept(saved);
      setDeletingConversations(previous => [{ ...deletingConversation, title: saved.title, version: saved.version }, ...previous.slice(1)]);
      setConversationDeleteError("对话仍存在，已读取最新版本。请核对运行和侧聊后再确认。");
      setConversationDeleteCheck(false);
    } catch (error) {
      if (error instanceof ConversationRequestError && error.status === 404) {
        conversations.forget(deletingConversation.id);
        if (deletingConversation.id === state.selectedId) router.push("/");
        setDeletingConversations(previous => previous.slice(1));
        setSelectedConversations(previous => previous.filter(id => id !== deletingConversation.id));
        setConversationDeleteCheck(false); setConversationDeleteError("已核对：该对话已不存在，其余尚未删除。");
        setFeedback("已核对：对话已不存在。");
      } else setConversationDeleteError(error instanceof Error ? error.message : "无法确认删除结果。");
    } finally { setConversationBusy(false); }
  }

  async function retryTitle(item: SpaceConversation) {
    if (conversationBusy || !item.version) return;
    setConversationBusy(true); setFeedback("");
    try {
      const saved = await generateConversationTitle({ session_id: item.id, version: item.version }, AbortSignal.timeout(20_000), true);
      conversations.accept(saved);
      setFeedback(saved.title_origin === "default" ? "名称生成未成功，对话不受影响；可稍后再次生成。" : "对话名称已更新。");
    } catch (error) { setFeedback(error instanceof Error ? error.message : "未能生成名称，对话不受影响。"); }
    finally { setConversationBusy(false); }
  }

  async function createBranch(messageId: string, mode: "before" | "after", draft = "", guarded = false) {
    if (!guarded && !window.dispatchEvent(new Event("careeract:before-navigate", { cancelable: true }))) {
      setLeaveAction(() => () => void createBranch(messageId, mode, draft, true));
      return;
    }
    if (branchLock.current || conversationBusy || sendBusy || runtimeRunning || !current.version || current.archived) {
      setFeedback("请先结束当前运行，再创建独立分支。");
      return;
    }
    branchLock.current = true;
    setConversationBusy(true); setFeedback("");
    try {
      const requestKey = `${current.id}:${messageId}:${mode}`;
      if (branchRequest.current?.key !== requestKey) branchRequest.current = { key: requestKey, id: crypto.randomUUID() };
      const saved = await createConversationBranch(current.id, { id: branchRequest.current.id, version: history.history?.session.version ?? current.version, message_id: messageId, mode, title: `${current.title.slice(0, 108)} · ${mode === "before" ? "编辑分支" : "独立分支"}` });
      conversations.accept(saved);
      if (draft) queueConversationSend(owner, saved.session_id, draft.trim());
      setMessageEdit(null);
      branchRequest.current = null;
      pendingNavigation.current = "/";
      store.update(previous => ({ ...previous, selectedId: saved.session_id, conversations: previous.conversations.map(item => item.id === saved.session_id ? { ...item, draft } : item) }));
      router.push("/");
      requestAnimationFrame(() => input.current?.focus());
    } catch (error) { setFeedback(error instanceof Error ? error.message : "分支创建未确认，原对话保持不变。"); }
    finally { branchLock.current = false; setConversationBusy(false); }
  }

  function select(id: string, guarded = false) {
    if (!guarded && id !== current.id && !window.dispatchEvent(new Event("careeract:before-navigate", { cancelable: true }))) {
      setMobileNavigation(false);
      setLeaveAction(() => () => select(id, true));
      return;
    }
    if ((runtimeRunning || sendBusy || conversationBusy) && id !== current.id) {
      setFeedback("请先停止当前运行，再切换对话。");
      return;
    }
    const selected = state.conversations.find(item => item.id === id)!;
    const destination = selected.archived ? "/" : selected.activeHref;
    pendingNavigation.current = destination;
    store.update(previous => ({ ...previous, selectedId: id, conversations: previous.conversations.map(item => item.id === id && item.archived ? { ...item, panelHidden: true } : item) }));
    router.push(destination);
    setContextOpen(false); setMobileNavigation(false); setFeedback("");
  }

  function openRoute(href: string, guarded = false) {
    if (href !== currentHref && !guarded && !window.dispatchEvent(new Event("careeract:before-navigate", { cancelable: true }))) {
      setMobileNavigation(false);
      setLeaveAction(() => () => openRoute(href, true));
      return;
    }
    sideChat.store.update(previous => ({ ...previous, hidden: true }));
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
    const destination = remaining.at(-1)?.href ?? "/";
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
        await conversations.persist(edit.id!, { title: edit.title.trim() });
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

  async function reconcileRun() {
    if (!history.activeRun || stopBusy) return;
    setStopBusy(true);
    try {
      await reconcileConversationRun(current.id, history.activeRun.run_id);
      setFeedback("已核对保存状态。中断结果仍未知，未重发原任务；请检查已保存内容后决定下一步。");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "运行核对失败，状态未改变。");
    } finally {
      setStopBusy(false);
      void history.refresh();
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (current.archived || (activeMessageEdit && !runtimeRunning)) return;
    if (runtimeRunning) {
      if (stopBusy) return;
      setStopBusy(true);
      stopRequested.current = true;
      setFeedback("正在停止本次运行，已保存的内容不会被删除。");
      try {
        await cancelConversationRun(current.id, history.activeRun?.run_id);
        aui.thread.cancelRun();
        setFeedback("已请求停止，请以服务端保存状态为准。");
      } catch (error) {
        setFeedback(error instanceof Error ? error.message : "停止结果未确认，请重新读取运行状态。");
      } finally {
        setStopBusy(false);
        void history.refresh();
      }
      return;
    }
    const text = current.draft.trim();
    if (!text || conversationBusy || sendBusy || history.loading || history.error) return;
    if (!current.version) {
      setConversationBusy(true);
      try {
        const saved = await conversations.persist(current.id);
        queueConversationSend(owner, saved.session_id, text);
        window.dispatchEvent(new Event("careeract:send-ready"));
      } catch (error) {
        setFeedback(error instanceof Error ? error.message : "未能确认对话，草稿仍保留。请重试。");
      } finally {
        setConversationBusy(false);
      }
      return;
    }
    void sendText(text, current.id);
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
    const destination = (pathname === `/projects/${id}` || pathname === `/workspace/projects/${id}`) ? "/" : currentHref;
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

  const orderedConversations = [...state.conversations].sort((left, right) => (right.createdAt ?? "9999").localeCompare(left.createdAt ?? "9999") || right.id.localeCompare(left.id));
  const listedConversations = orderedConversations.filter(item => !item.archived && !item.pinned && (item.version || item.draft || item.title !== "新对话"));
  const pinnedConversations = orderedConversations.filter(item => item.pinned && !item.archived);
  const recentConversations = listedConversations.filter(item => !item.projectId || !projects.some(project => project.id === item.projectId));
  const archivedConversations = orderedConversations.filter(item => item.archived);
  const visibleConversationIds = [
    ...pinnedConversations,
    ...projects.filter(item => !collapsed.includes(item.id)).flatMap(item => listedConversations.filter(conversation => conversation.projectId === item.id)),
    ...(recentExpanded ? recentConversations : []),
    ...(archiveExpanded ? archivedConversations : []),
  ].map(item => item.id);
  const selectedItems = orderedConversations.filter(item => selectedConversations.includes(item.id));

  function requestConversationDelete(items: SpaceConversation[]) {
    if (!items.length || conversationBusy || (runtimeRunning && items.some(item => item.id === current.id))) return;
    setConversationDeleteError(""); setConversationDeleteCheck(false); setDeletingConversations(items);
  }

  function beginRename(item: SpaceConversation) {
    if (conversationClick.current) clearTimeout(conversationClick.current);
    if (conversationBusy || busy) return;
    setEditingError(""); setEdit({ kind: "conversation", id: item.id, title: item.title });
  }

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

  const renderNavigation = (mobile = false) => (
    <nav className={styles.navigation} aria-label="职业项目与对话">
      <div className={styles.navigationHeader}><span className="text-sm font-semibold tracking-tight">CareerAct</span><Button ref={mobile ? undefined : collapseNavigation} variant="ghost" size="icon" className="hidden md:inline-flex" title="收起侧栏" aria-label="收起侧栏" aria-expanded onClick={toggleNavigation}><PanelLeft /></Button><Button variant="ghost" size="icon" className="md:hidden" aria-label="关闭项目导航" onClick={() => setMobileNavigation(false)}><X /></Button></div>
      <button className={styles.navButton} onClick={() => start()}><SquarePen />新对话</button>
      <button className={styles.navButton} onClick={showCapabilities}><Search />搜索能力<kbd className="ml-auto text-[10px] text-muted-foreground">Ctrl / ⌘ K</kbd></button>
      <button className={cn(styles.navButton, pathname === "/background" && panelOpen && !contextOpen && styles.selected)} aria-current={pathname === "/background" && panelOpen && !contextOpen ? "page" : undefined} onClick={() => openRoute("/background")}><BookOpen />职业背景</button>
      <button className={cn(styles.navButton, pathname === "/inbox" && panelOpen && !contextOpen && styles.selected)} aria-current={pathname === "/inbox" && panelOpen && !contextOpen ? "page" : undefined} onClick={() => openRoute("/inbox")}><MessageSquare />招聘沟通</button>
      <button className={cn(styles.navButton, pathname === "/library" && panelOpen && !contextOpen && styles.selected)} aria-current={pathname === "/library" && panelOpen && !contextOpen ? "page" : undefined} onClick={() => openRoute("/library")}><FileText />资料与成果</button>
      <div className={styles.navigationList} aria-busy={projectLoading || conversations.loading}>
      {selectingConversations && <div className={styles.selectionControls}>
          <span role="status">已选 {selectedItems.length} 段</span>
          <TooltipIconButton tooltip="删除选中对话" aria-label="删除选中对话" className="size-7" disabled={!selectedItems.length || conversationBusy || (runtimeRunning && selectedItems.some(item => item.id === current.id))} onClick={() => requestConversationDelete(selectedItems)}><Trash2 /></TooltipIconButton>
          <TooltipIconButton tooltip="取消选择" aria-label="取消选择" className="size-7" disabled={conversationBusy} onClick={() => { setSelectedConversations([]); setSelectingConversations(false); selectionAnchor.current = null; }}><X /></TooltipIconButton>
      </div>}
      {!!pinnedConversations.length && <section aria-label="置顶对话"><div className={styles.sectionHeading}>置顶</div>{pinnedConversations.map(renderConversation)}</section>}
      <div className={styles.sectionHeading}><span>项目</span><Button variant="ghost" size="icon" title="新建项目" aria-label="新建项目" onClick={() => { setMobileNavigation(false); setEditingError(""); setEdit({ kind: "create", id: crypto.randomUUID(), title: "" }); }}><Plus className="size-3.5" /></Button></div>
      {projectLoading && <p role="status" className="px-2 py-3 text-xs text-muted-foreground">正在读取项目…</p>}
      {projectError && <div className="px-2 py-3 text-xs"><p role="alert" className="leading-5 text-destructive">{projectError}</p><Button variant="ghost" size="sm" onClick={refreshProjects}>重新读取</Button></div>}
      {!projectLoading && !projectError && !projects.length && <p className="px-2 py-2 text-xs text-muted-foreground">暂无项目</p>}
      {projects.map(item => <section key={item.id} className="mb-2">
        <div className={cn(styles.sidebarActionRow, styles.projectRow)}>
          <button className={cn(styles.navButton, "min-w-0 flex-1")} aria-expanded={!collapsed.includes(item.id)} onClick={() => setCollapsed(previous => previous.includes(item.id) ? previous.filter(id => id !== item.id) : [...previous, item.id])}>
            <Folder /><span className="truncate" title={item.title}>{item.title}</span><ChevronDown className={cn("ml-auto !size-3", collapsed.includes(item.id) && "-rotate-90")} />
          </button>
          <div className={styles.sidebarActions}>
          <details className={styles.conversationMenu}>
            <summary aria-label={`${item.title}的项目操作`} title="项目操作"><MoreHorizontal className="size-3.5" /></summary>
            <div>
              <button onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); openRoute(`/projects/${item.id}`); }}>项目详情</button>
              <button onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); setMobileNavigation(false); setEditingError(""); setEdit({ kind: "project", id: item.id, title: item.title }); }}>重命名</button>
              <button className="text-destructive" onClick={event => { event.currentTarget.closest("details")?.removeAttribute("open"); requestDelete(item); }}>删除项目</button>
            </div>
          </details>
          <TooltipIconButton tooltip="新对话" aria-label={`在${item.title}中新建对话`} className="size-7" side="right" onClick={() => start(item.id)}><SquarePen className="size-3.5" /></TooltipIconButton>
          </div>
        </div>
        {!collapsed.includes(item.id) && listedConversations.filter(conversation => conversation.projectId === item.id).map(renderConversation)}
      </section>)}
      {projectCursor && <Button variant="ghost" size="sm" disabled={projectLoading} onClick={loadMoreProjects}>更多项目</Button>}
      {conversations.error && <div className="px-2 py-2 text-xs"><p role="alert" className="text-destructive">{conversations.error}</p><Button variant="ghost" size="sm" onClick={conversations.refresh}>重新读取对话</Button></div>}
      <Collapsible open={recentExpanded} onOpenChange={setRecentExpanded}>
        <div className={cn(styles.sidebarActionRow, styles.conversationSectionRow)}>
          <CollapsibleTrigger className={styles.conversationSection} aria-label="最近"><ChevronDown />最近</CollapsibleTrigger>
          <div className={styles.sidebarActions}><TooltipIconButton tooltip="新对话" aria-label="在最近中新建对话" className="size-7" side="right" onClick={() => start()}><SquarePen className="size-3.5" /></TooltipIconButton></div>
        </div>
        <CollapsibleContent>
          {recentConversations.map(renderConversation)}
          {!conversations.loading && !conversations.error && !recentConversations.length && <p className="px-2 py-2 text-xs text-muted-foreground">暂无最近对话</p>}
          {conversations.cursor && <Button variant="ghost" size="sm" disabled={conversations.loading} onClick={conversations.loadMore}>更多对话</Button>}
        </CollapsibleContent>
      </Collapsible>
      <Collapsible open={archiveExpanded} onOpenChange={setArchiveExpanded}>
        <CollapsibleTrigger className={styles.conversationSection} aria-label="归档"><ChevronDown />归档</CollapsibleTrigger>
        <CollapsibleContent>
          {archivedConversations.map(renderConversation)}
          {!conversations.loading && !conversations.error && !state.conversations.some(item => item.archived) && <p className="px-2 py-2 text-xs text-muted-foreground">没有已归档对话</p>}
          {conversations.cursor && <Button variant="ghost" size="sm" disabled={conversations.loading} onClick={conversations.loadMore}>更多归档对话</Button>}
        </CollapsibleContent>
      </Collapsible>
      </div>
      <div className={styles.navigationFooter}><AccountButton compact onClick={() => { setMobileNavigation(false); openAccount(); }} /></div>
    </nav>
  );

  return <div className={cn(styles.shell, !state.navigation && styles.noNavigation)}>
    <a href="#career-agent-input" className={styles.skipLink}>跳到对话输入</a>
    <aside className={styles.rail} aria-label="空间导航">
      <TooltipIconButton ref={expandNavigation} className="size-9" side="right" tooltip="展开侧栏" aria-label="展开侧栏" aria-expanded={false} onClick={toggleNavigation}><PanelLeft /></TooltipIconButton>
      <TooltipIconButton className="size-9" side="right" tooltip="新对话" aria-label="新对话" onClick={() => start()}><SquarePen /></TooltipIconButton>
      <TooltipIconButton className="size-9" side="right" tooltip="搜索能力 · Ctrl/⌘ K" aria-label="搜索能力" onClick={showCapabilities}><Search /></TooltipIconButton>
      <TooltipIconButton className="size-9" side="right" tooltip="职业背景" aria-label="职业背景" onClick={() => openRoute("/background")}><BookOpen /></TooltipIconButton>
      <TooltipIconButton className="size-9" side="right" tooltip="招聘沟通" aria-label="招聘沟通" onClick={() => openRoute("/inbox")}><MessageSquare /></TooltipIconButton>
      <TooltipIconButton className="size-9" side="right" tooltip="资料与成果" aria-label="资料与成果" onClick={() => openRoute("/library")}><FileText /></TooltipIconButton>
      <div className="mt-auto"><AccountButton compact onClick={openAccount} /></div>
    </aside>
    {renderNavigation()}
    <Dialog open={mobileNavigation} onOpenChange={setMobileNavigation}><DialogContent showCloseButton={false} className={styles.mobileDrawer} style={{ translate: "0 0" }}><DialogTitle className="sr-only">项目与对话</DialogTitle><DialogDescription className="sr-only">选择、创建或继续工作</DialogDescription>{renderNavigation(true)}</DialogContent></Dialog>
    <div ref={space} className={cn(styles.space, panelOpen && styles.withPanel)} style={{ "--panel-width": `${state.panelWidth}%` } as CSSProperties}>
      <main className={styles.agent}>
        <header className={styles.header}>
          <Button variant="ghost" size="icon" className="md:hidden" aria-label="打开项目导航" aria-expanded={mobileNavigation} onClick={() => setMobileNavigation(true)}><PanelLeft /></Button>
          <div className={styles.conversationHeading}>
            <span className={styles.conversationTitle} title={current.title}>{current.title}</span>
          </div>
          <TooltipIconButton className="size-9" tooltip="查看背景与引用" aria-label="查看上下文" aria-pressed={contextOpen} onClick={() => setContextOpen(value => !value)}><ListTree /></TooltipIconButton>
          <TooltipIconButton className="size-9" disabled={current.archived || !current.version || sideChat.busy} tooltip={current.archived ? "已归档对话不可开启侧聊" : sideChat.state.chat ? "打开临时侧聊" : "新建临时侧聊"} aria-label="打开临时侧聊" onClick={() => void sideChat.open()}><MessageSquarePlus /></TooltipIconButton>
          <TooltipIconButton className="size-9" disabled={!panelOpen && !routeOpen && !current.tabs.length} tooltip={panelOpen ? "收起内容区" : "展开内容区"} aria-label={panelOpen ? "收起内容区" : "展开内容区"} aria-expanded={panelOpen} onClick={() => { if (panelOpen) hideContent(); else if (routeOpen) update({ panelHidden: false }); else if (current.tabs.length) openRoute(current.tabs.at(-1)!.href); }}><PanelRight /></TooltipIconButton>
        </header>
        <div className={styles.startArea} aria-busy={history.loading}>
          {current.archived && <p role="status" className={styles.archiveNotice}><Archive className="size-4" />已归档 · 仅查看历史</p>}
          {history.error && <div className={styles.feedback}><p role="alert">{history.error}</p><Button variant="ghost" size="sm" onClick={history.refresh}>重新读取历史</Button></div>}
          {(runtimeHasMessages || history.history?.messages.length || history.history?.runs?.length || localRunning || sendBusy) && <ConversationHistory key={current.id} messages={history.history?.messages ?? []} runs={history.history?.runs} liveMessages={localRunning || sendBusy || !history.history ? runtimeMessages : undefined} isRunning={localRunning || sendBusy} onQuote={current.archived ? undefined : (id, quote) => void sideChat.open(id, quote)} onAddToConversation={current.archived ? undefined : text => { const draft = current.draft ? `${current.draft}\n\n${text}` : text; if (draft.length > 4000) { setFeedback("引用与草稿超过 4000 字，请精简后再添加；草稿已保留。"); return; } setContextOpen(false); store.update(previous => ({ ...previous, conversations: previous.conversations.map(item => item.id === current.id ? { ...item, draft } : item) })); requestAnimationFrame(() => input.current?.focus()); }} onEdit={runtimeRunning || conversationBusy || current.archived ? undefined : (id, text) => { setFeedback(""); setMessageEdit({ conversationId: current.id, id, text }); }} editing={activeMessageEdit ? { ...activeMessageEdit, busy: conversationBusy || runtimeRunning, error: feedback, onChange: text => setMessageEdit(previous => previous ? { ...previous, text } : null), onCancel: () => { setMessageEdit(null); setFeedback(""); requestAnimationFrame(() => input.current?.focus()); }, onSubmit: () => void createBranch(activeMessageEdit.id, "before", activeMessageEdit.text) } : undefined} onBranch={runtimeRunning || conversationBusy || current.archived || activeMessageEdit ? undefined : id => void createBranch(id, "after")} />}
          {sideChat.error && <p role="alert" className={styles.feedback}>{sideChat.error}</p>}
          {history.activeRun && !localRunning && <div className={styles.feedback}><p role="status">{["RUNNING", "PENDING"].includes(history.activeRun.status) ? "服务端运行尚未结束，可停止或重新读取状态。" : "运行状态需要核对，请勿重复发送。"}</p><Button variant="ghost" size="sm" onClick={history.refresh}>重新读取运行状态</Button><Button variant="ghost" size="sm" disabled={stopBusy} onClick={() => void reconcileRun()}>核对中断状态</Button><p>仅在确认没有执行进程后解除锁定；结果仍未知，不会重发。</p></div>}
          {history.history?.truncated && <p className={styles.feedback}>当前显示最近 100 条消息，更早内容仍保留。</p>}
          {!history.loading && !history.error && !history.history?.messages.length && !runtimeHasMessages && <div className={styles.welcome}><h1>{current.archived ? "已归档对话" : current.title}</h1></div>}
        </div>
          <div className={styles.composerArea}>
            {current.archived ? <div className={styles.archiveFooter}><span>历史和草稿已保留</span><Button variant="outline" size="sm" disabled={conversationBusy} onClick={() => void changeConversation(current.id, { archived: false })}><ArchiveRestore className="size-4" />恢复并继续对话</Button></div> : <><div className={styles.composerProject}>
              <AgentProjectPicker key={current.id} projects={projects} projectId={current.projectId} readOnly={current.archived || conversationBusy || runtimeRunning} loading={projectLoading} error={projectError} hasMore={!!projectCursor} onRefresh={() => void refreshProjects()} onLoadMore={() => void loadMoreProjects()} onChange={projectId => void changeConversation(current.id, { project_id: projectId })} onCreate={() => { setEditingError(""); setEdit({ kind: "create", id: crypto.randomUUID(), title: "" }); }} />
            </div>
            <form onSubmit={submit} className={styles.composer}>
              <label htmlFor="career-agent-input" className="sr-only">消息</label>
              <textarea id="career-agent-input" ref={input} rows={1} maxLength={4000} readOnly={current.archived || !!activeMessageEdit} value={current.draft} onChange={event => update({ draft: event.target.value })} onKeyDown={event => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }} placeholder="发送消息…" />
              <AgentComposerTools key={current.id} readOnly={current.archived} modelId={current.modelId} modelDisabled={runtimeRunning || conversationBusy || sendBusy || history.loading || !!history.error} onModelChange={id => void changeConversation(current.id, { model_id: id })}>
                <TooltipIconButton type="submit" variant="default" disabled={current.archived || (!!activeMessageEdit && !runtimeRunning) || conversationBusy || stopBusy || history.loading || !!history.error || (!runtimeRunning && (sendBusy || !current.draft.trim()))} tooltip={runtimeRunning ? "停止运行" : "发送 · Ctrl/⌘ Enter"} aria-label={runtimeRunning ? "停止运行" : "发送"} side="top" className="size-8 rounded-full">{runtimeRunning ? <Square className="size-3 fill-current" /> : <ArrowUp />}</TooltipIconButton>
              </AgentComposerTools>
            </form></>}
          {feedback && <p role="status" className={styles.feedback}>{feedback}</p>}
          {!store.storageAvailable() && <p role="alert" className={styles.feedback}>此浏览器无法保留草稿，请勿关闭页面。</p>}
          </div>
      </main>
      <SideChatPanel controller={sideChat} hidden={current.archived} mainCheckpoint={sideChat.state.chat?.side_context.source_id === current.id ? mainCheckpoint : null} />
      {(routeOpen || contextOpen) && <>{panelOpen && <div role="separator" aria-label="调整内容区宽度" aria-orientation="vertical" tabIndex={0} aria-valuemin={30} aria-valuemax={65} aria-valuenow={state.panelWidth} className={styles.resizeHandle} onKeyDown={event => { if (event.key === "ArrowLeft" || event.key === "ArrowRight") { event.preventDefault(); store.update(previous => ({ ...previous, panelWidth: Math.min(65, Math.max(30, previous.panelWidth + (event.key === "ArrowLeft" ? 2 : -2))) })); } }} onPointerDown={event => event.currentTarget.setPointerCapture(event.pointerId)} onPointerMove={event => { if (!event.currentTarget.hasPointerCapture(event.pointerId)) return; const bounds = space.current?.getBoundingClientRect(); if (bounds) store.update(previous => ({ ...previous, panelWidth: Math.min(65, Math.max(30, (bounds.right - event.clientX) / bounds.width * 100)) })); }} onPointerUp={event => event.currentTarget.releasePointerCapture(event.pointerId)} />}
      <aside className={cn(styles.content, !panelOpen && styles.hiddenContent)} aria-label="内容工作区"><div className={styles.tabBar}><Button variant="ghost" size="icon" className="md:hidden shrink-0" aria-label="打开项目导航" aria-expanded={mobileNavigation} onClick={() => setMobileNavigation(true)}><PanelLeft /></Button><div role="tablist" aria-label="打开的内容" className={styles.tabList} onKeyDown={event => { if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return; const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')); const selected = buttons.indexOf(document.activeElement as HTMLButtonElement); if (selected < 0) return; event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : (selected + (event.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length; buttons[next]?.focus(); buttons[next]?.click(); }}>{visibleTabs.map(tab => <div key={tab.href} className={cn(styles.tab, !contextOpen && tab.href === currentHref && styles.activeTab)}><button role="tab" tabIndex={!contextOpen && tab.href === currentHref ? 0 : -1} aria-selected={!contextOpen && tab.href === currentHref} aria-controls="space-content" id={`tab-${tab.href}`} title={tab.label} onClick={() => openRoute(tab.href)}><FileText className="size-3.5" /><span className="truncate">{tab.label}</span></button><button title={`关闭${tab.label}`} aria-label={`关闭${tab.label}标签`} onClick={() => closeTab(tab.href)}><X className="size-3" /></button></div>)}{contextOpen && <div className={cn(styles.tab, styles.activeTab)}><button role="tab" aria-selected aria-controls="space-content" id="tab-context"><ListTree className="size-3.5" />引用范围</button><button aria-label="关闭引用范围标签" onClick={() => setContextOpen(false)}><X className="size-3" /></button></div>}</div><Button variant="ghost" size="icon" title="收起并保留内容" aria-label="收起内容区并保留标签" onClick={hideContent}><PanelRight /></Button></div>
        <div id="space-content" role="tabpanel" aria-labelledby={contextOpen ? "tab-context" : `tab-${currentHref}`} className={styles.surface}>
          {contextOpen && <article className={styles.document}>
            <h2>引用范围</h2>
            <section>
              <h3>个人背景与长期规则</h3>
              <p>不同对话和项目共用同一份已确认背景与通用规则，Agent 按需读取相关内容。</p>
              <div className="flex flex-wrap gap-2"><Button variant="outline" size="sm" onClick={() => openRoute("/background")}>职业背景</Button><Button variant="outline" size="sm" onClick={() => openRoute("/assistant")}>规则与笔记</Button></div>
            </section>
            <section>
              <h3>项目补充 · {projectLabel}</h3>
              <p>{project ? project.purpose || "尚未填写项目目标。" : current.projectId ? "暂时无法读取关联项目，请核对项目列表。" : "仍可使用个人背景与长期规则。关联项目后，额外使用该项目的目标和规则。"}</p>
              {project && <Button variant="outline" size="sm" onClick={() => openRoute(`/projects/${project.id}`)}>项目详情</Button>}
            </section>
            <section>
              <h3>本次引用</h3>
              <p>{history.history?.messages.length ? "历史引用需按当次工作记录核对。" : "此对话尚无已保存的运行消息。"}打开内容标签不会自动把正文发送给模型。</p>
              <Button variant="outline" size="sm" onClick={() => openRoute("/library")}>查看资料与成果</Button>
            </section>
          </article>}
          <div className={cn(styles.routeContent, contextOpen && styles.hiddenContent)}>{children}</div>
        </div>
      </aside></>}
    </div>
    <Dialog open={!!deletingConversations.length} onOpenChange={open => { if (!open && !conversationBusy) setDeletingConversations([]); }}><DialogContent>
      <DialogHeader><DialogTitle>{deletingConversations.length > 1 ? `删除 ${deletingConversations.length} 段对话？` : "删除对话？"}</DialogTitle><DialogDescription>将永久删除下列对话的历史、运行记录和本标签页草稿。项目、材料、已保存规则与独立分支保留，已发生的外部操作不会撤销。此操作无法恢复；逐项删除，失败时停止并核对。</DialogDescription></DialogHeader>
      <ul className="max-h-48 overflow-auto text-sm">{deletingConversations.map(item => <li key={item.id} className="break-words py-1">{item.title}</li>)}</ul>
      {conversationDeleteError && <p role="alert" className="text-sm text-destructive">{conversationDeleteError}</p>}
      <div className="flex justify-end gap-2"><Button variant="outline" disabled={conversationBusy} onClick={() => setDeletingConversations([])}>取消</Button>
        {conversationDeleteCheck ? <Button disabled={conversationBusy} onClick={() => void checkConversationDelete()}>重新读取并核对</Button> : <Button variant="destructive" disabled={conversationBusy} onClick={() => void confirmConversationDelete()}>{conversationBusy ? "正在删除…" : "删除对话"}</Button>}
      </div>
    </DialogContent></Dialog>
    <Dialog open={!!deleting} onOpenChange={value => { if (!value && !deleteBusy) setDeleting(null); }}>
      <DialogContent>
        <DialogHeader><DialogTitle>删除项目？</DialogTitle><DialogDescription>将永久删除“{deleting?.title}”。对话与材料会保留并解除项目关联，项目规则与笔记会停用，已保存的职业背景不受影响。此操作无法撤销。</DialogDescription></DialogHeader>
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
    <Dialog open={!!edit && edit.kind !== "conversation"} onOpenChange={value => { if (!value && !busy) setEdit(null); }}><DialogContent><DialogHeader><DialogTitle>{edit?.kind === "create" ? "新建项目" : "重命名"}</DialogTitle><DialogDescription>按你的职业目标组织工作，目标可以稍后补充。</DialogDescription></DialogHeader><form onSubmit={saveEdit} className="space-y-4"><label htmlFor="space-name" className="block text-sm">名称</label><input id="space-name" autoFocus required maxLength={120} value={edit?.title ?? ""} disabled={busy} onChange={event => setEdit(previous => previous ? { ...previous, title: event.target.value } : null)} className="h-10 w-full rounded-md border bg-background px-3 text-sm" />{editingError && <p role="alert" className="text-sm text-destructive">{editingError}</p>}<div className="flex justify-end gap-2"><Button type="button" variant="ghost" disabled={busy} onClick={() => setEdit(null)}>取消</Button><Button type="submit" disabled={busy || !edit?.title.trim()}>{busy ? "正在保存…" : "保存"}</Button></div></form></DialogContent></Dialog>
  </div>;

  function renderConversation(item: SpaceConversation) {
    const selected = selectedConversations.includes(item.id);
    return <div key={item.id} className={cn(styles.conversationRow, item.id === state.selectedId && styles.selected, selected && styles.batchSelected)}>
      {edit?.kind === "conversation" && edit.id === item.id ? <form className={styles.inlineRename} onSubmit={saveEdit}>
        <input autoFocus aria-label="对话名称" maxLength={120} required disabled={busy} value={edit.title} onFocus={event => event.currentTarget.select()} onChange={event => setEdit(previous => previous ? { ...previous, title: event.target.value } : null)} onKeyDown={event => { if (event.key === "Escape" && !busy) { event.preventDefault(); setEdit(null); } }} />
        <Button type="submit" variant="ghost" size="sm" disabled={busy || !edit.title.trim()}>{busy ? "保存中" : "保存"}</Button>
        <TooltipIconButton type="button" tooltip="取消重命名 · Esc" aria-label="取消重命名" className="size-6" disabled={busy} onClick={() => setEdit(null)}><X /></TooltipIconButton>
        {editingError && <p role="alert" className="w-full text-xs text-destructive">{editingError}</p>}
      </form> : <>
      <button aria-current={item.id === state.selectedId ? "page" : undefined} aria-pressed={selectingConversations ? selected : undefined} onDoubleClick={() => { if (!selectingConversations) beginRename(item); }} onKeyDown={event => {
        if (event.key === "F2") { event.preventDefault(); beginRename(item); }
        if (event.key === "Delete") { event.preventDefault(); requestConversationDelete(selectedItems.length ? selectedItems : [item]); }
        if (event.key === "Escape") { setSelectingConversations(false); setSelectedConversations([]); }
      }} onClick={event => {
        if (conversationBusy) return;
        if (conversationClick.current) clearTimeout(conversationClick.current);
        if (selectingConversations || event.ctrlKey || event.metaKey || event.shiftKey) {
          setSelectingConversations(true);
          setSelectedConversations(previous => selectConversationRange(visibleConversationIds, previous, selectionAnchor.current, item.id, event.shiftKey, event.ctrlKey || event.metaKey));
          if (!event.shiftKey) selectionAnchor.current = item.id;
        } else {
          selectionAnchor.current = item.id;
          if (event.detail < 2) conversationClick.current = setTimeout(() => { void select(item.id); }, event.detail === 0 ? 0 : 350);
        }
      }} className={styles.conversationLink} title={item.title}>
        {selectingConversations && <span aria-hidden="true" className={styles.selectionMark}>{selected ? "✓" : ""}</span>}<span className="truncate">{item.title}</span>{item.draft && <span className={styles.draftMark}>草稿</span>}
      </button>
      {!selectingConversations && <div className={styles.conversationActions}>
        {item.titleOrigin === "default" && item.titleGenerationAttempted && <TooltipIconButton tooltip="重新生成名称" aria-label={`重新生成${item.title}的名称`} className="size-6" disabled={conversationBusy} onClick={() => void retryTitle(item)}><RotateCcw /></TooltipIconButton>}
        {!item.archived && item.pinned !== undefined && <TooltipIconButton tooltip={item.pinned ? "取消置顶" : "置顶"} aria-label={`${item.pinned ? "取消置顶" : "置顶"}${item.title}`} aria-pressed={!!item.pinned} className="size-6" disabled={conversationBusy} onClick={() => void changeConversation(item.id, { pinned: !item.pinned })}>{item.pinned ? <PinOff /> : <Pin />}</TooltipIconButton>}
        <TooltipIconButton tooltip={item.archived ? "恢复对话" : "归档对话"} aria-label={`${item.archived ? "恢复" : "归档"}${item.title}`} className="size-6" disabled={conversationBusy || (item.id === current.id && runtimeRunning)} onClick={() => void changeConversation(item.id, { archived: !item.archived })}>{item.archived ? <ArchiveRestore /> : <Archive />}</TooltipIconButton>
      </div>}
      </>}
    </div>;
  }
}

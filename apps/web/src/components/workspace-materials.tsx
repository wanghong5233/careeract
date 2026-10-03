"use client";

import { useEffect, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { useAuiState } from "@assistant-ui/react";
import { ArrowUpRight, Check, Copy, FileText, LoaderCircle, Plus, RefreshCw } from "lucide-react";

import { useWorkspaceActions } from "@/components/workspace-actions";
import { useDraftGuard } from "@/hooks/use-draft-guard";
import { useConfirmAction } from "@/hooks/use-confirm-action";
import { Button } from "@/components/ui/button";
import { associateAgentSession } from "@/lib/agent-work-sessions";
import {
  MaterialRequestError, readMaterial, readMaterials, resolveMaterialProposal,
  saveMaterialVersion, type CareerMaterial, type MaterialReference,
} from "@/lib/materials";
import { cn } from "@/lib/utils";

function References({ items }: { items: MaterialReference[] }) {
  return <div className="space-y-3 text-sm">{items.length ? items.map(item => <p key={`${item.type}-${item.id}-${item.version}`} className="break-words">{item.title}<span className="ml-2 text-xs text-muted-foreground">版本 {item.version.slice(0, 8)}</span></p>) : <p className="text-muted-foreground">依据本次委托提供的合成内容，未引用已确认档案。材料表达不会自动成为职业事实。</p>}</div>;
}

export function WorkspaceMaterials({ review = false }: { review?: boolean }) {
  const { openAgent, describeContent } = useWorkspaceActions();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const running = useAuiState(state => state.thread.isRunning);
  const [items, setItems] = useState<CareerMaterial[]>([]);
  const selectedId = searchParams.get("material");
  const [loadedMaterial, setSelected] = useState<CareerMaterial | null>(null);
  const selected = loadedMaterial?.id === selectedId ? loadedMaterial : null;
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [mode, setMode] = useState(review ? "改动" : "正文");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const [error, setError] = useState("");
  const [listError, setListError] = useState("");
  const [detailError, setDetailError] = useState<{ id: string; message: string } | null>(null);
  const { requestConfirmation, confirmation } = useConfirmAction();
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [needsCheck, setNeedsCheck] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [listAttempt, setListAttempt] = useState(0);
  const dirty = editing && Boolean(selected) && draft !== (selected?.current_version?.body ?? "");
  useDraftGuard(dirty || busy);

  useEffect(() => {
    if (running) return;
    const controller = new AbortController();
    readMaterials(undefined, AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]))
      .then(page => {
        if (controller.signal.aborted) return;
        setItems(page.items); setNextCursor(page.next_cursor); setListError("");
      })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setListError(failure instanceof Error ? failure.message : "材料列表无法读取。"); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [listAttempt, running]);

  useEffect(() => {
    if (!selectedId || running || (editing && loadedMaterial?.id === selectedId)) return;
    const controller = new AbortController();
    readMaterial(selectedId, AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]))
      .then(value => {
        if (controller.signal.aborted) return;
        setSelected(value); setEditing(false); setNeedsCheck(false); setDetailError(null);
      })
      .catch((failure: unknown) => { if (!controller.signal.aborted) { setSelected(null); setDetailError({ id: selectedId, message: failure instanceof Error ? failure.message : "材料无法读取。" }); } })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false); });
    return () => controller.abort();
  }, [selectedId, attempt, running, editing, loadedMaterial?.id]);

  useEffect(() => {
    if (!selected) return;
    describeContent({ href: `${pathname}?${searchParams}`, label: selected.title });
  }, [describeContent, pathname, searchParams, selected]);

  function selectMaterial(id: string) {
    const url = new URL(window.location.href);
    url.searchParams.set("material", id);
    window.history.pushState(null, "", url);
  }

  function refresh() {
    if (busy) return;
    const reload = () => {
      setEditing(false); setError(""); setListError(""); setDetailError(null); setLoading(true);
      setDetailLoading(Boolean(selectedId)); setSelected(null); setAttempt(value => value + 1); setListAttempt(value => value + 1);
    };
    if (dirty) requestConfirmation(reload, "重新读取会放弃未保存的精确修正，是否继续？");
    else reload();
  }

  function changeMaterial(id: string) {
    if (busy || id === selectedId) return;
    const select = () => { setEditing(false); selectMaterial(id); setNotice(""); setError(""); };
    if (dirty) requestConfirmation(select, "切换会放弃未保存的精确修正，是否继续？");
    else select();
  }

  async function delegate(create = false) {
    if (busy || running || listError) return;
    if (dirty) { setNotice("请先保存或取消精确修正，再交还 Agent。"); return; }
    setBusy(true); setError("");
    try {
      if (selected && !create) await associateAgentSession(selected.project_id, AbortSignal.timeout(15_000));
      const prompt = selected && !create
        ? `请用 read_material 读取材料 ${selected.id} 的当前版本，再根据我的反馈提出修改。我的反馈：\n\n不要添加未提供的职业事实；用 propose_material_edit 保存待审阅提议，不自动接受。`
        : "请帮我创作一份合成文本材料。先问我用途、希望表达的内容和事实边界，再用 propose_new_material 保存待审阅草稿。不要读取真实私人资料，不自动接受。";
      openAgent(prompt);
    } catch (failure) { setError(failure instanceof Error ? failure.message : "Agent 关联失败，本次未委托。"); }
    finally { setBusy(false); }
  }

  async function resolve(proposalId: string, state: "accepted" | "rejected") {
    if (!selected || dirty || busy || needsCheck) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const value = await resolveMaterialProposal(selected.id, proposalId, state, AbortSignal.timeout(20_000));
      setSelected(value); setNotice(state === "accepted" ? "已接受并保存新版本。职业事实与投递授权没有改变。" : "已拒绝提议，正文未改变。");
      setListAttempt(value => value + 1);
      if (state === "accepted") setMode("正文");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "处理结果未确认，请重新读取核对。");
      setNeedsCheck(true);
    } finally { setBusy(false); }
  }

  async function save() {
    if (!selected?.current_version || busy || needsCheck || !dirty || !draft.trim()) return;
    setBusy(true); setError("");
    try {
      const value = await saveMaterialVersion(selected.id, { base_version_id: selected.current_version.id, body: draft }, AbortSignal.timeout(20_000));
      setSelected(value); setEditing(false); setNotice("精确修正已保存为新版本。"); setListAttempt(value => value + 1);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "保存结果未确认，请重新读取核对；输入仍保留。");
      if (!(failure instanceof MaterialRequestError) || failure.status !== 422) setNeedsCheck(true);
    } finally { setBusy(false); }
  }

  async function loadMore() {
    if (!nextCursor || busy) return;
    setBusy(true);
    try { const page = await readMaterials(nextCursor, AbortSignal.timeout(20_000)); setItems(current => [...current, ...page.items.filter(item => !current.some(existing => existing.id === item.id))]); setNextCursor(page.next_cursor); }
    catch (failure) { setListError(failure instanceof Error ? failure.message : "更多材料无法读取。"); }
    finally { setBusy(false); }
  }

  const pending = selected?.proposals.filter(item => item.state === "pending") ?? [];
  const initialDraft = selected?.current_version?.source === "seed";
  const shownBody = initialDraft ? pending[0]?.proposed_body ?? "草稿已拒绝，可反馈给 Agent 重新创作。" : selected?.current_version?.body;
  const readError = listError || (detailError?.id === selectedId ? detailError?.message : "");
  const visibleError = readError || error;
  if (visibleError && !selected && !items.length) return <section className="mx-auto max-w-lg py-8">
    <FileText className="mb-5 size-6 text-muted-foreground" />
    <h1 className="text-xl font-medium tracking-tight">资料与成果</h1>
    <p role="alert" className="mt-4 text-sm leading-7 text-muted-foreground">{visibleError}</p>
    <p className="mt-2 text-xs leading-6 text-muted-foreground">暂时无法载入材料。恢复后，你可以在这里查看正文、审阅改动和追溯版本。</p>
    <Button className="mt-6" variant="outline" onClick={refresh} disabled={busy}>重新读取</Button>
  </section>;
  return <>
    {confirmation}
    <header className="mb-6 flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-2xl font-semibold tracking-tight">{review ? "材料审阅" : "资料与成果"}</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">Agent 主创，你用反馈打磨，再审阅与接受。</p></div><Button variant="outline" disabled={busy || running || loading || Boolean(readError)} onClick={() => void delegate(true)}><Plus className="size-4" />请 Agent 创作</Button></header>
    <p className="mb-5 text-xs leading-5 text-muted-foreground">合成文本实验 · 内容保存在服务端，委托时会交给已配置模型。真实文件与私人资料尚未开放。</p>
    {visibleError && <div role="alert" className="mb-4 rounded-lg border border-destructive/30 p-4 text-sm"><p>{visibleError}</p><Button className="mt-3" size="sm" variant="outline" onClick={refresh} disabled={busy}>重新读取核对</Button></div>}
    {notice && <p role="status" className="mb-4 text-sm text-muted-foreground">{notice}</p>}
    <div className="grid min-h-[32rem] overflow-hidden rounded-xl border md:grid-cols-[12rem_minmax(0,1fr)]">
      <aside className="border-b bg-muted/20 p-3 md:border-b-0 md:border-r"><div className="mb-3 flex items-center justify-between px-2"><span className="text-xs text-muted-foreground">我的成果</span><Button size="icon" variant="ghost" className="size-8" aria-label="刷新材料" onClick={refresh} disabled={busy}><RefreshCw className="size-3.5" /></Button></div>{loading && !items.length ? <p role="status" className="p-2 text-sm text-muted-foreground">正在读取…</p> : items.map(item => <button key={item.id} disabled={busy} aria-pressed={selectedId === item.id} onClick={() => changeMaterial(item.id)} className={cn("mb-1 flex min-h-10 w-full items-start gap-2 rounded-md px-2 py-2 text-left text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring", selectedId === item.id ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted/60")}><FileText className="mt-0.5 size-4 shrink-0" /><span className="break-words">{item.title}</span></button>)}{nextCursor && <Button size="sm" variant="ghost" onClick={() => void loadMore()} disabled={busy}>加载更多</Button>}</aside>
      <section className="min-w-0">
        {detailLoading || (selectedId && !selected && !readError) ? <div role="status" className="flex items-center gap-2 p-8 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />恢复材料与提议…</div> : !selected ? readError ? <p className="p-8 text-sm text-muted-foreground">材料未能载入，请重新读取。</p> : <div className="flex min-h-[28rem] flex-col items-center justify-center px-6 text-center"><FileText className="mb-4 size-6 text-muted-foreground" /><h2 className="text-lg font-medium">从一个想法到一份成果</h2><p className="mt-3 max-w-sm text-sm leading-6 text-muted-foreground">告诉 Agent 用途和内容，它创作草稿；你审阅、反馈并接受，正文和历史会留在这里。</p><Button className="mt-6" onClick={() => void delegate(true)} disabled={busy || running || loading}>告诉 Agent 你的想法<ArrowUpRight className="size-4" /></Button></div> : <>
          <div className="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4"><div><h2 className="text-base font-medium break-words">{selected.title}</h2><p className="mt-1 text-xs text-muted-foreground">{initialDraft ? "草稿 · 尚未接受" : `已接受版本 v${selected.current_version?.number}`}{pending.length ? ` · ${pending.length} 条待审阅` : ""}</p></div><Button onClick={() => void delegate()} disabled={busy || running || dirty} size="sm">继续打磨<ArrowUpRight className="size-3.5" /></Button></div>
          <div role="group" aria-label="材料视图" className="flex flex-wrap gap-1 border-b px-4 py-2">{["正文", "改动", "来源", "版本"].map(view => <button key={view} disabled={busy || editing} onClick={() => setMode(view)} aria-pressed={view === mode} className={cn("min-h-9 rounded-md px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring", view === mode ? "bg-muted font-medium" : "text-muted-foreground hover:bg-muted/50")}>{view}{view === "改动" && pending.length ? ` · ${pending.length}` : ""}</button>)}</div>
          {mode === "正文" && <div className="p-5 sm:p-7">{editing ? <><label htmlFor="material-body" className="mb-3 block text-xs text-muted-foreground">精确修正 · 保存前仅保留在当前页面</label><textarea id="material-body" value={draft} onChange={event => setDraft(event.target.value)} maxLength={40000} className="min-h-72 w-full rounded-md border bg-background p-4 text-[15px] leading-7 outline-none focus:ring-2 focus:ring-ring" /><div className="mt-4 flex justify-end gap-2"><Button variant="ghost" onClick={() => { if (dirty) requestConfirmation(() => setEditing(false), "取消修正会放弃未保存的输入，是否继续？"); else setEditing(false); }} disabled={busy}>取消修正</Button><Button onClick={() => void save()} disabled={!dirty || !draft.trim() || busy || needsCheck}>保存新版本</Button></div></> : <><p className="whitespace-pre-wrap break-words text-[15px] leading-7">{shownBody}</p><div className="mt-7 flex flex-wrap justify-end gap-2">{!initialDraft && <><Button size="sm" variant="ghost" onClick={async () => { try { await navigator.clipboard.writeText(selected.current_version?.body ?? ""); setNotice("已复制纯文本。"); } catch { setError("复制失败，可选择正文复制。"); } }}><Copy className="size-3.5" />复制纯文本</Button><Button size="sm" variant="ghost" disabled={busy || running || needsCheck} onClick={() => { setDraft(selected.current_version?.body ?? ""); setEditing(true); }}>精确修正</Button></>}{pending.length > 0 && <Button size="sm" variant="outline" onClick={() => setMode("改动")}>审阅修改</Button>}</div></>}</div>}
          {mode === "改动" && <div className="divide-y">{pending.length ? pending.map(proposal => <article key={proposal.id} className="p-5 sm:p-7"><div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="text-sm font-medium">{proposal.base_number === 0 ? "Agent 创作的草稿" : `基于 v${proposal.base_number} 的修改`}</h3><span className="text-xs text-muted-foreground">{proposal.stale ? "基准已变化 · 请重新打磨" : "待你审阅"}</span></div><p className="my-3 text-sm leading-6 text-muted-foreground">{proposal.rationale || "请核对表达和事实边界。"}</p><pre aria-label="材料修改 Diff" className="max-h-96 overflow-y-auto rounded-lg bg-muted/40 p-4 text-sm leading-6 whitespace-pre-wrap break-words">{proposal.diff.map((line, index) => <span key={index} className={cn("block", line.startsWith("+") && !line.startsWith("+++") ? "bg-emerald-500/10" : line.startsWith("-") && !line.startsWith("---") ? "bg-red-500/10" : "text-muted-foreground")}>{line || " "}</span>)}</pre><details className="mt-4 text-xs"><summary className="cursor-pointer text-muted-foreground">本次来源与版本</summary><div className="mt-3"><References items={proposal.references} /></div></details><div className="mt-5 flex flex-wrap justify-end gap-2"><Button variant="ghost" size="sm" onClick={() => void delegate()} disabled={busy || running}>反馈给 Agent</Button><Button variant="outline" size="sm" onClick={() => void resolve(proposal.id, "rejected")} disabled={busy || needsCheck}>拒绝提议</Button><Button size="sm" onClick={() => void resolve(proposal.id, "accepted")} disabled={busy || needsCheck || proposal.stale}><Check className="size-3.5" />接受这一版</Button></div></article>) : <div className="p-7"><p className="text-sm font-medium">没有待审阅修改</p><p className="mt-2 text-sm text-muted-foreground">告诉 Agent 哪里要改，它会读取当前版本再提出修改。</p></div>}</div>}
          {mode === "来源" && <div className="p-7"><h3 className="mb-4 text-sm font-medium">当前版本的创作依据</h3><References items={selected.current_version?.references ?? []} /><p className="mt-6 text-xs leading-5 text-muted-foreground">这里记录实际读取的对象版本，不能证明模型表达中的每一句都是已验证事实。原始文件和段落级引用尚未开放。</p></div>}
          {mode === "版本" && <div className="divide-y">{selected.versions.filter(version => version.number > 0).map(version => <details key={version.id} className="p-5"><summary className="cursor-pointer text-sm">v{version.number} · {version.source === "agent" ? "接受 Agent 提议" : "用户保存"}{version.id === selected.current_version_id ? " · 当前" : ""}</summary><p className="mt-4 whitespace-pre-wrap break-words text-sm leading-7">{version.body}</p><div className="mt-4"><References items={version.references} /></div></details>)}{selected.proposals.filter(proposal => proposal.state !== "pending").map(proposal => <details key={proposal.id} className="p-5"><summary className="cursor-pointer text-sm">{proposal.state === "accepted" ? "已接受" : "已拒绝"}的提议 · 基于 v{proposal.base_number}</summary><p className="mt-3 whitespace-pre-wrap break-words text-sm leading-7">{proposal.proposed_body}</p><p className="mt-3 text-xs text-muted-foreground">{proposal.rationale}</p></details>)}{initialDraft && !selected.proposals.some(proposal => proposal.state !== "pending") && <p className="p-7 text-sm text-muted-foreground">接受第一份草稿后，版本会从 v1 开始保留。</p>}</div>}
        </>}
      </section>
    </div>
  </>;
}

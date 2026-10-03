"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, ArrowUpRight, LoaderCircle, Plus } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { AgentAction } from "@/components/workspace-actions";
import { useDraftGuard } from "@/hooks/use-draft-guard";
import { useConfirmAction } from "@/hooks/use-confirm-action";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import {
  createProject, projectPrompt, projectStatusLabels, ProjectRequestError,
  readProject, readProjects, updateProject,
  type CareerProject, type ProjectContent,
} from "@/lib/projects";
import { associateAgentSession } from "@/lib/agent-work-sessions";

const inputClass = "h-10 w-full rounded-md border bg-background px-3 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring";

function Failure({ message, children }: { message: string; children?: React.ReactNode }) {
  return <div role="alert" className="my-4 space-y-3 rounded-lg border border-destructive/30 p-4 text-sm">
    <p>{message}</p>{children}
  </div>;
}

export function WorkspaceProjects() {
  const router = useRouter();
  const [projects, setProjects] = useState<CareerProject[]>([]);
  const [cursor, setCursor] = useState<string>();
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [draftId, setDraftId] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [purpose, setPurpose] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState("");
  const { requestConfirmation, confirmation } = useConfirmAction();
  useDraftGuard(Boolean(draftId && (title || purpose || saving)));

  useEffect(() => {
    const refresh = () => { setCursor(undefined); setLoading(true); setAttempt(value => value + 1); };
    window.addEventListener("careeract:projects-changed", refresh);
    return () => window.removeEventListener("careeract:projects-changed", refresh);
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    readProjects({ cursor }, AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]))
      .then(page => {
        if (controller.signal.aborted) return;
        setProjects(current => cursor
          ? [...current, ...page.items.filter(item => !current.some(existing => existing.id === item.id))]
          : page.items);
        setNextCursor(page.next_cursor);
        setLoadError("");
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setLoadError(error instanceof Error ? error.message : "暂时无法读取项目。");
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [cursor, attempt]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!draftId || !title.trim() || saving) return;
    setSaving(true);
    setSaveError("");
    try {
      const project = await createProject({ id: draftId, title: title.trim(), purpose: purpose.trim() }, AbortSignal.timeout(20_000));
      setDraftId(null);
      setTitle("");
      setPurpose("");
      window.dispatchEvent(new Event("careeract:projects-changed"));
      router.push(`/workspace/projects/${project.id}`);
    } catch (error: unknown) {
      setSaveError(error instanceof Error ? error.message : "尚不能确认保存结果，请核对项目。");
    } finally {
      setSaving(false);
    }
  }

  return <>
    {confirmation}
    <header className="mb-7 flex flex-wrap items-start justify-between gap-4">
      <div className="max-w-xl"><h1 className="text-2xl font-semibold tracking-tight">职业项目</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">一个阶段目标，一组持续推进的工作，以及可以带到下一阶段的成果。</p></div>
      <div className="flex flex-wrap gap-2">
        <AgentAction prompt="我想建立一个职业项目。请先问我阶段目标、时间范围、约束和成功标准，整理项目建议；当前尚无项目写入工具，不要声称已保存。">交给 Agent</AgentAction>
        <Button variant="outline" disabled={Boolean(draftId)} onClick={() => setDraftId(crypto.randomUUID())}><Plus className="size-4" />新建项目</Button>
      </div>
    </header>
    {draftId && <form onSubmit={save} className="mt-5 space-y-4 rounded-xl border p-5">
      <div><h2 className="text-sm font-medium">留下一项值得持续推进的目标</h2><p className="mt-1 text-xs leading-5 text-muted-foreground">只需标题与意图；详细计划可以交给 Agent 形成。</p></div>
      <label className="block space-y-2 text-sm"><span>项目标题</span><input autoFocus required maxLength={200} disabled={saving} value={title} onChange={event => setTitle(event.target.value)} className={inputClass} /></label>
      <label className="block space-y-2 text-sm"><span>想推进什么</span><Textarea rows={3} maxLength={4000} disabled={saving} value={purpose} onChange={event => setPurpose(event.target.value)} /></label>
      {saveError && <Failure message={saveError}><Link href={`/workspace/projects/${draftId}`} className="underline underline-offset-4">核对这个项目</Link><p className="text-xs text-muted-foreground">输入未丢失；用同一份内容重试不会重复创建。</p></Failure>}
      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="ghost" disabled={saving} onClick={() => {
          const discard = () => { setDraftId(null); setTitle(""); setPurpose(""); setSaveError(""); };
          if (title || purpose) requestConfirmation(discard, "放弃当前输入？若之前保存结果未知，请先核对项目。");
          else discard();
        }}>取消</Button>
        <Button type="submit" disabled={saving || !title.trim()}>{saving && <LoaderCircle className="size-4 animate-spin" />}保存项目</Button>
      </div>
    </form>}
    {loadError && <Failure message={loadError}><Button variant="outline" size="sm" onClick={() => { setLoadError(""); setLoading(true); setAttempt(value => value + 1); }}>重新读取</Button></Failure>}
    {projects.length > 0 && <div className="mt-5 divide-y rounded-xl border">
      {projects.map(project => <Link key={project.id} href={`/workspace/projects/${project.id}`} className="group block p-5 outline-none hover:bg-muted/30 focus-visible:ring-2 focus-visible:ring-ring">
        <div className="flex items-start justify-between gap-3"><h2 className="min-w-0 break-words text-base font-medium">{project.title}</h2><span className="shrink-0 text-xs text-muted-foreground">{projectStatusLabels[project.status]}</span></div>
        <p className="mt-2 line-clamp-3 whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">{project.purpose || "目标待澄清"}</p>
        <div className="mt-4 flex items-center justify-between text-xs text-muted-foreground"><span>最近更新 {new Date(project.updated_at).toLocaleDateString("zh-CN")}</span><span className="inline-flex items-center gap-1">继续项目<ArrowUpRight className="size-3" /></span></div>
      </Link>)}
    </div>}
    {loading ? <p role="status" className="my-8 flex items-center justify-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />正在读取项目…</p>
      : !loadError && projects.length === 0 ? <div className="my-8 rounded-xl border px-5 py-12 text-center"><h2 className="font-medium">从一个值得推进的目标开始</h2><p className="mx-auto mt-2 max-w-sm text-sm leading-6 text-muted-foreground">求职、代表作、能力提升与入职成长，都可以成为持续空间。</p></div> : null}
    {!loading && !loadError && nextCursor && <Button variant="outline" className="mt-5" onClick={() => { setLoading(true); setCursor(nextCursor); }}>加载更多项目</Button>}
  </>;
}

export function WorkspaceProjectDetail({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<CareerProject | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    readProject(projectId, AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)]))
      .then(value => { if (!controller.signal.aborted) { setProject(value); setError(""); } })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "暂时无法读取项目。"); });
    return () => controller.abort();
  }, [projectId, attempt]);
  return <>
    <Link href="/workspace/projects" className="mb-6 inline-flex items-center gap-2 text-xs text-muted-foreground underline underline-offset-4"><ArrowLeft className="size-3" />全部项目</Link>
    {error ? <Failure message={error}><Button variant="outline" size="sm" onClick={() => { setError(""); setAttempt(value => value + 1); }}>重新读取</Button></Failure>
      : project ? <ProjectWork key={project.id} initial={project} />
        : <p role="status" className="flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />正在恢复项目…</p>}
  </>;
}

function contentOf(project: CareerProject): ProjectContent {
  return { title: project.title, purpose: project.purpose, status: project.status };
}

function ProjectWork({ initial }: { initial: CareerProject }) {
  const [saved, setSaved] = useState(initial);
  const [draft, setDraft] = useState(contentOf(initial));
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [needsCheck, setNeedsCheck] = useState(false);
  const [latest, setLatest] = useState<CareerProject | null>(null);
  const [notice, setNotice] = useState("");
  const [sessionError, setSessionError] = useState("");
  const { requestConfirmation, confirmation } = useConfirmAction();
  const normalized = { ...draft, title: draft.title.trim(), purpose: draft.purpose.trim() };
  const dirty = editing && JSON.stringify(normalized) !== JSON.stringify(contentOf(saved));
  useDraftGuard(dirty || busy);

  useEffect(() => {
    const controller = new AbortController();
    associateAgentSession(saved.id, controller.signal).then(() => setSessionError("")).catch((error: unknown) => {
      if (!controller.signal.aborted) setSessionError(error instanceof Error ? error.message : "Agent 工作关联暂时无法保存。");
    });
    return () => controller.abort();
  }, [saved.id]);

  function accept(project: CareerProject) {
    setSaved(project); setDraft(contentOf(project)); setEditing(false);
    setNeedsCheck(false); setLatest(null); setError(""); setNotice("项目已保存。");
    window.dispatchEvent(new Event("careeract:projects-changed"));
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (!dirty || !normalized.title || busy || needsCheck) return;
    setBusy(true); setError(""); setNotice("");
    try {
      accept(await updateProject(saved.id, { ...normalized, version: saved.version }, AbortSignal.timeout(20_000)));
    } catch (failure: unknown) {
      setError(failure instanceof Error ? failure.message : "保存结果尚未核实，请读取最新版本。");
      setNeedsCheck(!(failure instanceof ProjectRequestError) || [0, 409, 502, 503].includes(failure.status));
    } finally { setBusy(false); }
  }

  async function checkLatest() {
    if (busy) return;
    setBusy(true);
    try {
      const current = await readProject(saved.id, AbortSignal.timeout(20_000));
      if (JSON.stringify(contentOf(current)) === JSON.stringify(normalized)) accept(current);
      else { setLatest(current); setError(""); }
    } catch (failure: unknown) {
      setError(failure instanceof Error ? failure.message : "暂时无法核对最新版本。");
    } finally { setBusy(false); }
  }

  return <div className="space-y-7">
    {confirmation}
    <header><div className="flex flex-wrap items-start justify-between gap-4"><h1 className="min-w-0 break-words text-2xl font-semibold tracking-tight">{saved.title}</h1><span className="rounded-full bg-muted px-3 py-1 text-xs">{projectStatusLabels[saved.status]}</span></div><p className="mt-3 text-xs text-muted-foreground">最近保存 {new Date(saved.updated_at).toLocaleString("zh-CN")}</p></header>
    <section className="border-y py-6"><div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-sm font-medium">当前目标</h2><Button variant="ghost" size="sm" disabled={editing || busy} onClick={() => { setEditing(true); setNotice(""); }}>精确修正</Button></div>
      {!editing && <><p className="mt-4 whitespace-pre-wrap break-words text-sm leading-7">{saved.purpose || "目标还没有明确，可以先交给 Agent。"}</p><div className="mt-5"><AgentAction variant="outline" prompt={projectPrompt(saved)}>交给 Agent 继续推进</AgentAction></div></>}
      {editing && <form onSubmit={save} className="mt-4 space-y-4">
        <label className="block space-y-2 text-sm"><span>项目标题</span><input autoFocus required maxLength={200} disabled={busy} className={inputClass} value={draft.title} onChange={event => setDraft(value => ({ ...value, title: event.target.value }))} /></label>
        <label className="block space-y-2 text-sm"><span>想推进什么</span><Textarea rows={5} maxLength={4000} disabled={busy} value={draft.purpose} onChange={event => setDraft(value => ({ ...value, purpose: event.target.value }))} /></label>
        {error && <Failure message={error} />}
        {needsCheck && !latest && <Button type="button" variant="outline" disabled={busy} onClick={checkLatest}>核对最新版本</Button>}
        {latest && <aside className="space-y-3 rounded-lg border bg-muted/30 p-4 text-sm"><h3 className="font-medium">当前保存的最新内容</h3><p className="break-words">{latest.title} · {projectStatusLabels[latest.status]}</p><p className="whitespace-pre-wrap break-words leading-6 text-muted-foreground">{latest.purpose || "目标待澄清"}</p><p className="text-xs leading-5">你的输入仍在上方。继续修改后保存，会以当前输入替换这份最新内容。</p><div className="flex flex-wrap gap-2"><Button type="button" variant="outline" size="sm" onClick={() => { setSaved(latest); setLatest(null); setNeedsCheck(false); }}>基于最新版本继续修改</Button><Button type="button" variant="ghost" size="sm" onClick={() => accept(latest)}>采用最新内容</Button></div></aside>}
        <div className="flex flex-wrap justify-end gap-2"><Button type="button" variant="ghost" disabled={busy} onClick={() => {
          const discard = () => { setDraft(contentOf(saved)); setEditing(false); setError(""); setLatest(null); setNeedsCheck(false); };
          if (dirty || needsCheck) requestConfirmation(discard, "结束编辑会放弃当前输入。保存结果未知时请先核对，是否继续？");
          else discard();
        }}>结束编辑</Button><Button type="submit" disabled={busy || !dirty || !normalized.title || needsCheck}>{busy && <LoaderCircle className="size-4 animate-spin" />}保存修改</Button></div>
      </form>}
      {notice && <p role="status" className="mt-4 text-sm">{notice}</p>}
    </section>
    <section><h2 className="text-sm font-medium">共同工作</h2><p className="mt-3 text-sm leading-6 text-muted-foreground">先围绕目标讨论。项目关联任务、材料与成果将在下一步接入，对话目前不会自动写入项目。</p><div className="mt-4 flex flex-wrap gap-4">{[["tasks", "任务工作面"], ["library", "资料与成果"], ["plan", "阶段计划"]].map(([path, label]) => <Link key={path} href={`/workspace/${path}`} className="text-xs underline underline-offset-4">{label}</Link>)}</div></section>
    {sessionError && <p role="alert" className="text-sm text-destructive">{sessionError}</p>}
  </div>;
}

"use client";

import { useEffect, useState, type FormEvent } from "react";
import { CheckCircle2, LoaderCircle, Pencil, Plus, RotateCcw, Save, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { AgentAction } from "@/components/workspace-actions";
import { type CareerProfile, type ProfileContent, type ProfileEntry, profileSections } from "@/lib/profile";

const inputClass = "h-10 w-full rounded-md border bg-background px-3 text-sm outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 disabled:opacity-60";

async function readProfile(signal?: AbortSignal): Promise<CareerProfile> {
  const response = await fetch("/api/profile", { cache: "no-store", signal });
  if (!response.ok) {
    throw new Error(response.status === 401 ? "登录已失效，请重新登录。" : "暂时无法读取档案，请稍后重试。");
  }
  return response.json();
}

export function ProfileEditor() {
  const [profile, setProfile] = useState<CareerProfile | null>(null);
  const [loadError, setLoadError] = useState("");
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    readProfile(AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)])).then(result => {
      if (!controller.signal.aborted) setProfile(result);
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setLoadError(error instanceof Error ? error.message : "读取失败，请重试。");
    });
    return () => controller.abort();
  }, [loadAttempt]);

  if (!profile) {
    return (
      <div className="rounded-xl border bg-background p-8" role={loadError ? "alert" : "status"}>
        {loadError ? (
          <div className="space-y-4">
            <p>{loadError}</p>
            <Button variant="outline" onClick={() => { setLoadError(""); setLoadAttempt(loadAttempt + 1); }}>重新读取</Button>
            <a href="/sign-in" className="ml-4 text-sm underline">前往登录</a>
          </div>
        ) : <p className="flex items-center gap-2 text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />正在读取你的职业档案…</p>}
      </div>
    );
  }
  return <ProfileForm initialProfile={profile} />;
}

function ProfileForm({ initialProfile }: { initialProfile: CareerProfile }) {
  const [saved, setSaved] = useState(initialProfile);
  const [draft, setDraft] = useState(initialProfile.content);
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [mustReload, setMustReload] = useState(false);
  const [editing, setEditing] = useState(false);
  const dirty = JSON.stringify(draft) !== JSON.stringify(saved.content);
  const entryCount = draft.education.length + draft.experience.length + draft.projects.length;

  useEffect(() => {
    if (!dirty) return;
    function preventLoss(event: BeforeUnloadEvent) { event.preventDefault(); }
    window.addEventListener("beforeunload", preventLoss);
    return () => window.removeEventListener("beforeunload", preventLoss);
  }, [dirty]);

  function updateDraft(next: ProfileContent) {
    setDraft(next);
    setConfirmed(false);
    setMessage("");
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!confirmed || busy || mustReload) return;
    setBusy(true);
    setMessage("");
    setError("");
    try {
      const response = await fetch("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: draft, version: saved.version, confirmed: true }),
        signal: AbortSignal.timeout(20_000),
      });
      if (!response.ok) {
        setMustReload(response.status === 409 || response.status >= 500);
        setError(response.status === 409
          ? "档案已在其他页面更新。你的输入仍保留；请先核对服务器版本，避免覆盖新内容。"
          : response.status === 401 || response.status === 403
            ? "登录验证失败。输入仍保留，请在另一标签页重新登录后再保存。"
            : response.status === 422
              ? "请检查必填项及字段长度，确认后重新保存。"
              : "保存结果尚未确认。输入仍保留，请重新读取服务器版本核对。");
        return;
      }
      const result: CareerProfile = await response.json();
      setSaved(result);
      setDraft(result.content);
      setConfirmed(false);
      setMessage("已保存并确认，刷新页面后仍可查看。");
      setEditing(false);
    } catch {
      setMustReload(true);
      setError("连接中断，保存结果尚未确认。输入仍保留，请重新读取服务器版本核对。");
    } finally {
      setBusy(false);
    }
  }

  async function reload() {
    if (dirty && !window.confirm("重新读取会替换当前未保存的输入。请先复制需要保留的内容，是否继续？")) return;
    setBusy(true);
    try {
      const result = await readProfile(AbortSignal.timeout(15_000));
      setSaved(result);
      setDraft(result.content);
      setConfirmed(false);
      setMustReload(false);
      setError("");
      setMessage("已读取服务器最新版本。");
    } catch (failure: unknown) {
      setError(failure instanceof Error ? failure.message : "读取失败，输入已保留。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-7">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-xl"><h1 className="text-2xl font-semibold tracking-tight">职业背景</h1><p className="mt-2 text-sm leading-6 text-muted-foreground">事实、能力证据、目标与约束，作为不同职业阶段共享的背景。</p></div>
        <div className="flex flex-wrap gap-2"><AgentAction variant="outline" prompt="我想整理我的职业背景。我会讲述经历，请先提取事实、证据、目标和约束；不要假定你已经读取工作区，也不要声称已保存档案。">向伙伴讲述</AgentAction><Button variant="ghost" className="h-9" disabled={busy} onClick={() => {
          if (editing && dirty) {
            if (!window.confirm("退出精确编辑会放弃未保存的修改，是否继续？")) return;
            setDraft(saved.content);
            setConfirmed(false);
          }
          setEditing(value => !value);
        }}><Pencil className="size-3.5" />{editing ? "返回阅读" : "精确修正"}</Button></div>
      </header>
      {!editing ? <ProfileReading profile={saved} message={message} /> : <form onSubmit={save} className="space-y-6">
      <section className="grid gap-4 rounded-xl border bg-background p-5 sm:grid-cols-3" aria-label="档案概览">
        <div><p className="text-xs text-muted-foreground">档案状态</p><p className="mt-2 font-medium">{dirty ? "有未保存修改" : saved.version ? "已确认" : "尚未建立"}</p></div>
        <div><p className="text-xs text-muted-foreground">教育、经历与成果</p><p className="mt-2 font-medium">{entryCount} 条记录{dirty ? "（含未保存）" : ""}</p></div>
        <div><p className="text-xs text-muted-foreground">最近确认</p><p className="mt-2 text-sm">{saved.confirmed_at ? new Date(saved.confirmed_at).toLocaleString("zh-CN") : "从一段经历开始"}</p></div>
      </section>
      {!saved.version && <p className="rounded-lg bg-muted/60 p-4 text-sm leading-6">先记录你已确认的经历，再逐步补充成果和证据。无需一次填完所有内容；这份档案会成为后续材料与职业建议的事实来源。</p>}
      <fieldset disabled={busy} className="min-w-0 space-y-6 disabled:opacity-70">
        <section className="rounded-xl border bg-background p-5 sm:p-6">
          <h2 className="mb-4 text-lg font-semibold">关于你</h2>
          <label className="block max-w-md space-y-2 text-sm"><span>姓名或称呼</span><input className={inputClass} autoComplete="name" maxLength={100} value={draft.display_name} onChange={event => updateDraft({ ...draft, display_name: event.target.value })} /></label>
        </section>
        {profileSections.map(section => (
          <section key={section.key} id={section.key} className="rounded-xl border bg-background p-5 sm:p-6">
            <div className="mb-5 flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold">{section.label}</h2>
              <Button type="button" variant="outline" size="sm" disabled={draft[section.key].length >= 30} onClick={() => updateDraft({ ...draft, [section.key]: [...draft[section.key], { title: "", organization: "", period: "", details: "", evidence: "" }] })}><Plus className="size-4" />添加记录</Button>
            </div>
            {!draft[section.key].length && <p className="text-sm text-muted-foreground">还没有{section.label}记录，按需要添加。</p>}
            <div className="space-y-5">
              {draft[section.key].map((entry, index) => {
                function changeEntry(field: keyof ProfileEntry, value: string) {
                  updateDraft({ ...draft, [section.key]: draft[section.key].map((current, position) => position === index ? { ...current, [field]: value } : current) });
                }
                return (
                  <fieldset key={index} className="min-w-0 rounded-lg border bg-muted/20 p-4">
                    <legend className="px-2 text-sm font-medium">{section.label} {index + 1}</legend>
                    <div className="grid gap-4 sm:grid-cols-2">
                      <label className="space-y-2 text-sm"><span>{section.titleLabel} *</span><input required maxLength={200} className={inputClass} value={entry.title} onChange={event => changeEntry("title", event.target.value)} /></label>
                      <label className="space-y-2 text-sm"><span>{section.organizationLabel}</span><input maxLength={200} className={inputClass} value={entry.organization} onChange={event => changeEntry("organization", event.target.value)} /></label>
                      <label className="space-y-2 text-sm sm:col-span-2"><span>时间范围</span><input maxLength={100} placeholder="例如：2024.09—至今" className={inputClass} value={entry.period} onChange={event => changeEntry("period", event.target.value)} /></label>
                      <label className="space-y-2 text-sm sm:col-span-2"><span>事实与成果</span><Textarea rows={3} maxLength={4000} placeholder="描述你实际做过什么、承担的职责和可核实的成果。" value={entry.details} onChange={event => changeEntry("details", event.target.value)} /></label>
                      <label className="space-y-2 text-sm sm:col-span-2"><span>证据或来源（可选）</span><Textarea rows={2} maxLength={1000} placeholder="例如：项目仓库链接、报告名称或证书说明。" value={entry.evidence} onChange={event => changeEntry("evidence", event.target.value)} /></label>
                    </div>
                    <Button type="button" variant="ghost" size="sm" className="mt-3 text-muted-foreground" aria-label={`移除${section.label}第${index + 1}条`} onClick={() => { if (window.confirm("从当前编辑内容移除这条记录？保存并确认后才会生效。")) updateDraft({ ...draft, [section.key]: draft[section.key].filter((_entry, position) => position !== index) }); }}><Trash2 className="size-4" />移除记录</Button>
                  </fieldset>
                );
              })}
            </div>
          </section>
        ))}
        {([
          ["skills", "技能与能力", "记录你掌握的技能、熟悉程度及实际使用场景。"],
          ["goals", "当前职业目标", "例如：求职方向、期望岗位、城市和时间安排。"],
          ["constraints", "选择边界与约束", "例如：到岗时间、城市限制，以及不能接受的工作条件。"],
        ] as const).map(([key, label, placeholder]) => (
          <section key={key} className="rounded-xl border bg-background p-5 sm:p-6">
            <label className="block space-y-4"><span className="text-lg font-semibold">{label}</span><Textarea rows={4} maxLength={4000} placeholder={placeholder} value={draft[key]} onChange={event => updateDraft({ ...draft, [key]: event.target.value })} /></label>
          </section>
        ))}
        <label className="flex items-start gap-3 rounded-lg border p-4 text-sm leading-6"><input type="checkbox" className="mt-1 size-4 shrink-0" checked={confirmed} onChange={event => setConfirmed(event.target.checked)} /><span>我已核对本次内容，确认它准确表达我的经历、目标与约束。保存只更新职业档案，不会发送申请。</span></label>
      </fieldset>
      <div className="sticky bottom-0 z-10 space-y-3 rounded-xl border bg-background/95 p-4 shadow-sm backdrop-blur">
        {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
        {message && <p role="status" className="flex items-center gap-2 text-sm text-emerald-700"><CheckCircle2 className="size-4 shrink-0" />{message}</p>}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <span className="text-xs text-muted-foreground">{dirty ? "修改尚未保存，离开前请先确认保存。" : "仅保存你明确确认的内容。"}</span>
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" disabled={busy} onClick={reload}><RotateCcw className="size-4" />重新读取</Button>
            <Button type="submit" disabled={busy || !confirmed || mustReload || (!dirty && !!saved.version)}>{busy ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}保存并确认</Button>
          </div>
        </div>
      </div>
    </form>}
    </div>
  );
}

function ProfileReading({ profile, message }: { profile: CareerProfile; message: string }) {
  const content = profile.content;
  return <div className="space-y-8">
    <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-y py-3 text-xs text-muted-foreground"><span>{profile.version ? "已确认档案" : "尚未建立档案"}</span><span>{profile.confirmed_at ? "最近确认 · " + new Date(profile.confirmed_at).toLocaleString("zh-CN") : "先讲述，再核对事实"}</span></div>
    {message && <p role="status" className="flex items-center gap-2 text-sm"><CheckCircle2 className="size-4" />{message}</p>}
    {!profile.version && <div className="rounded-xl border px-6 py-7"><h2 className="text-lg font-medium">从你已经拥有的经历开始</h2><p className="mt-2 max-w-xl text-sm leading-6 text-muted-foreground">不必一次填完所有字段。先向伙伴讲述或提供内容，再审阅整理结果。Agent 更新与导入尚未接入；当前可通过“精确修正”保存已确认事实。</p></div>}
    {content.display_name && <h2 className="text-xl font-medium">{content.display_name}</h2>}
    {profileSections.map(section => <section key={section.key} className="border-b pb-7"><h2 className="mb-4 text-sm font-medium">{section.label}</h2>{content[section.key].length ? <div className="space-y-6">{content[section.key].map((entry, index) => <article key={index} className="min-w-0"><div className="flex flex-wrap justify-between gap-2"><h3 className="text-base font-medium break-words">{entry.title}</h3><span className="text-xs text-muted-foreground">{entry.period}</span></div>{entry.organization && <p className="mt-1 text-sm text-muted-foreground">{entry.organization}</p>}{entry.details && <p className="mt-3 whitespace-pre-wrap break-words text-sm leading-7">{entry.details}</p>}{entry.evidence && <details className="mt-3 text-xs leading-6 text-muted-foreground"><summary className="w-fit cursor-pointer rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring">查看证据与来源</summary><p className="mt-2 whitespace-pre-wrap break-words">{entry.evidence}</p></details>}</article>)}</div> : <p className="text-sm text-muted-foreground">尚未记录</p>}</section>)}
    {([["skills", "技能与能力"], ["goals", "当前目标"], ["constraints", "选择边界与约束"]] as const).map(([key, label]) => <section key={key}><h2 className="mb-3 text-sm font-medium">{label}</h2><p className="whitespace-pre-wrap break-words text-sm leading-7 text-muted-foreground">{content[key] || "尚未记录"}</p></section>)}
  </div>;
}

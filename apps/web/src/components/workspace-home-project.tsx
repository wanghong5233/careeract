"use client";

import Link from "next/link";
import { FolderKanban, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { readProjects, projectStatusLabels, type CareerProject } from "@/lib/projects";

export function WorkspaceHomeProject() {
  const [project, setProject] = useState<CareerProject | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    readProjects({ archived: false, limit: 1 }, AbortSignal.any([controller.signal, AbortSignal.timeout(20_000)])).then(page => {
      if (!controller.signal.aborted) { setProject(page.items[0] ?? null); setError(""); }
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "暂时无法读取当前项目。");
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [attempt]);

  return <section aria-labelledby="current-project-heading" className="border-y py-7">
    <div className="flex items-center justify-between gap-4">
      <h2 id="current-project-heading" className="text-sm font-medium">最近职业项目</h2>
      <Link href="/workspace/projects" className="text-xs text-muted-foreground underline underline-offset-4">全部项目</Link>
    </div>
    {loading ? <p role="status" className="mt-6 flex items-center gap-2 text-sm text-muted-foreground"><LoaderCircle className="size-4 animate-spin" />正在读取项目…</p>
      : error ? <div className="mt-6 flex flex-wrap items-center gap-3 text-sm"><p role="alert" className="text-destructive">{error}</p><Button variant="outline" size="sm" onClick={() => { setLoading(true); setError(""); setAttempt(value => value + 1); }}>重新读取</Button></div>
        : <div className="mt-6 flex items-start gap-4">
          <FolderKanban className="mt-1 size-5 shrink-0 text-muted-foreground" />
          <div className="min-w-0 max-w-xl">
            <h3 className="break-words text-lg font-medium">{project?.title ?? "从一个值得持续推进的目标开始"}</h3>
            <p className="mt-2 whitespace-pre-wrap break-words text-sm leading-6 text-muted-foreground">{project ? project.purpose || "目标待澄清，可以先和伙伴讨论。" : "寻找下一份工作、打磨代表作，或积累一段新经历。先把想法告诉伙伴，再逐步形成计划和成果。"}</p>
            {project && <p className="mt-2 text-xs text-muted-foreground">{projectStatusLabels[project.status]} · 最近保存 {new Date(project.updated_at).toLocaleDateString("zh-CN")}</p>}
            <div className="mt-5"><Link href={project ? `/workspace/projects/${project.id}` : "/workspace/projects"} className="text-sm underline underline-offset-4">{project ? "继续这个项目" : "建立第一个项目"}</Link></div>
          </div>
        </div>}
  </section>;
}

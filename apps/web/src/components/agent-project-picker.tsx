"use client";

import { useState } from "react";
import { Popover } from "@base-ui/react/popover";
import { Check, Folder, Plus, Search, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import type { CareerProject } from "@/lib/projects";
import styles from "./agent-space.module.css";

export function AgentProjectPicker({ projects, projectId, readOnly, loading, error, hasMore, onRefresh, onLoadMore, onChange, onCreate }: {
  projects: CareerProject[];
  projectId: string | null;
  readOnly: boolean;
  loading: boolean;
  error: string;
  hasMore: boolean;
  onRefresh: () => void;
  onLoadMore: () => void;
  onChange: (projectId: string | null) => void;
  onCreate: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selected = projects.find(project => project.id === projectId);
  const filtered = projects.filter(project => project.title.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  function choose(next: string | null) {
    onChange(next);
    setOpen(false);
  }

  return <Popover.Root open={open} onOpenChange={value => { setOpen(value); if (!value) setQuery(""); }}>
    <TooltipProvider><Tooltip>
      <TooltipTrigger render={<Popover.Trigger render={<Button type="button" variant="ghost" size={projectId ? "sm" : "icon"} disabled={readOnly} aria-label={projectId ? `切换项目：${selected?.title ?? "项目暂不可用"}` : "选择项目"} className={styles.projectTrigger} />} />}>
        <Folder className="size-3.5 shrink-0" />{projectId && <span className="truncate">{selected?.title ?? "项目暂不可用"}</span>}
      </TooltipTrigger>
      <TooltipContent side="top">{projectId ? "切换项目" : "选择项目"}</TooltipContent>
    </Tooltip></TooltipProvider>
    <Popover.Portal><Popover.Positioner side="top" align="start" sideOffset={8} className="z-50">
      <Popover.Popup className={styles.projectPopover}>
        <Popover.Title className="sr-only">选择项目</Popover.Title>
        <label className={styles.projectSearch}><Search className="size-3.5" /><input type="search" aria-label="搜索项目" placeholder="搜索项目" value={query} onChange={event => setQuery(event.target.value)} /></label>
        <div className={styles.projectOptions}>
          {filtered.map(project => <button type="button" key={project.id} className={styles.composerMenuItem} aria-pressed={project.id === projectId} onClick={() => choose(project.id)}><Folder /><span className="truncate">{project.title}</span>{project.id === projectId && <Check className="ml-auto" />}</button>)}
          {!filtered.length && <p className="px-3 py-4 text-xs text-muted-foreground">{loading ? "正在读取项目…" : error ? "项目读取失败" : query.trim() ? "没有匹配的项目" : "暂无项目"}</p>}
          {error && <div className="px-3 pb-2"><p role="alert" className="text-xs text-destructive">{error}</p><Button type="button" size="sm" variant="ghost" disabled={loading} onClick={onRefresh}>重试</Button></div>}
          {hasMore && <Button type="button" size="sm" variant="ghost" className="w-full" disabled={loading} onClick={onLoadMore}>{loading ? "正在读取…" : "加载更多"}</Button>}
        </div>
        <div className="mt-1 border-t pt-1">
          <button type="button" className={styles.composerMenuItem} onClick={() => { setOpen(false); onCreate(); }}><Plus />新建项目</button>
          {projectId && <button type="button" className={styles.composerMenuItem} onClick={() => choose(null)}><X />移出项目</button>}
        </div>
      </Popover.Popup>
    </Popover.Positioner></Popover.Portal>
  </Popover.Root>;
}

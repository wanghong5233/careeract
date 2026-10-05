"use client";

import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { pendingSelection } from "@/lib/material-review";
import type { MaterialProposal } from "@/lib/materials";

export function MaterialProposalReview({ proposal, selection, rewrites, busy, running, needsCheck, onToggle, onRewrite, onResolve, onDelegate }: {
  proposal: MaterialProposal;
  selection?: string[];
  rewrites: Record<string, string>;
  busy: boolean;
  running: boolean;
  needsCheck: boolean;
  onToggle: (identifier: string, checked: boolean) => void;
  onRewrite: (identifier: string, value: string) => void;
  onResolve: (state: "accepted" | "rejected", changeId?: string) => void;
  onDelegate: (changeId: string) => void;
}) {
  const selected = pendingSelection(proposal, selection);
  const base = Array.from(proposal.base_body);
  return <article className="p-5 sm:p-7">
    <div className="flex flex-wrap items-baseline justify-between gap-2"><h3 className="text-sm font-medium">{proposal.base_number === 0 ? "Agent 创作的草稿" : `基于 v${proposal.base_number} 的修改`}</h3><span className="text-xs text-muted-foreground">{proposal.stale ? "基准已变化 · 请重新打磨" : "待你审阅"}</span></div>
    <p className="my-3 text-sm leading-6 text-muted-foreground">{proposal.rationale || "请核对表达和事实边界。"}</p>
    <div className="space-y-4">{proposal.changes.map((change, index) => <section key={change.id} className="min-w-0 rounded-lg border p-3 text-sm">
      <label className="flex items-center gap-2"><input aria-label={`选择修改 ${index + 1}`} type="checkbox" checked={selected.includes(change.id)} disabled={change.state !== "pending" || busy || needsCheck} onChange={event => onToggle(change.id, event.target.checked)} /><span>修改 {index + 1} · {change.state === "accepted" ? "已接受" : change.state === "rejected" ? "已拒绝" : "待审阅"}</span></label>
      <p className="mt-2 whitespace-pre-wrap break-words leading-7"><span className="text-muted-foreground">{base.slice(Math.max(0, change.start - 24), change.start).join("")}</span><del className="bg-red-500/10 decoration-red-600">{change.original || "∅"}</del><ins className="bg-emerald-500/10 decoration-emerald-600">{change.replacement || "∅"}</ins><span className="text-muted-foreground">{base.slice(change.end, change.end + 24).join("")}</span></p>
      {change.state === "pending" && <div className="mt-3 space-y-2"><label className="block text-xs text-muted-foreground" htmlFor={`${proposal.id}-${change.id}`}>精确改写 · 保存后仍待审阅</label><textarea id={`${proposal.id}-${change.id}`} aria-label={`改写修改 ${index + 1}`} value={rewrites[change.id] ?? change.replacement} maxLength={4000} onChange={event => onRewrite(change.id, event.target.value)} className="min-h-16 w-full rounded-md border bg-background p-2 leading-6 outline-none focus-visible:ring-2 focus-visible:ring-ring" /><div className="flex flex-wrap justify-end gap-2"><Button size="sm" variant="ghost" disabled={busy || running || needsCheck || proposal.stale} onClick={() => onDelegate(change.id)}>请 Agent 改写这处</Button><Button size="sm" variant="outline" disabled={busy || needsCheck || proposal.stale || rewrites[change.id] === undefined || rewrites[change.id] === change.replacement} onClick={() => onResolve("accepted", change.id)}>保存待审改写</Button></div></div>}
      {change.revisions?.length ? <details className="mt-3 text-xs"><summary className="cursor-pointer text-muted-foreground">被替代的建议 · {change.revisions.length} 次</summary>{change.revisions.map((revision, revisionIndex) => <p key={revisionIndex} className="mt-2 whitespace-pre-wrap break-words">{revision.replacement || "∅"}<span className="ml-2 text-muted-foreground">审阅版本 {revision.review_version.slice(0, 8)}</span></p>)}</details> : null}
    </section>)}</div>
    <details className="mt-4"><summary className="cursor-pointer text-sm text-muted-foreground">组合预览 · 包含未接受建议</summary><p className="mt-3 whitespace-pre-wrap break-words text-sm leading-7">{proposal.review_body}</p></details>
    <details className="mt-4 text-xs"><summary className="cursor-pointer text-muted-foreground">提议来源与版本</summary><p className="mt-2">基准 v{proposal.base_number} · 审阅 {proposal.review_version?.slice(0, 8)}</p>{proposal.references.length ? proposal.references.map((reference, index) => <p key={index} className="mt-2 break-words">{reference.title} · {reference.version.slice(0, 8)}</p>) : <p className="mt-2 text-muted-foreground">合成输入，未引用已确认档案。接受表达不等于确认事实或授权投递。</p>}</details>
    <div className="mt-5 flex flex-wrap justify-end gap-2"><Button variant="outline" size="sm" onClick={() => onResolve("rejected")} disabled={busy || needsCheck || !selected.length}>拒绝所选</Button><Button size="sm" onClick={() => onResolve("accepted")} disabled={busy || needsCheck || proposal.stale || !selected.length}><Check className="size-3.5" />接受所选</Button></div>
  </article>;
}

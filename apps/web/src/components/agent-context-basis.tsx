"use client";

import { useAuiState } from "@assistant-ui/react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";

type ContextReference = { type?: string; id?: string; title: string; version: string };
type Basis = { run_id: string | null; references: ContextReference[]; proposals: ContextReference[] };

export function AgentContextBasis() {
  const running = useAuiState(state => state.thread.isRunning);
  const [basis, setBasis] = useState<Basis | null>(null);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (running) return;
    const controller = new AbortController();
    fetch("/api/agent/basis", { cache: "no-store", signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]) })
      .then(async response => {
        if (response.status === 404) return null;
        if (!response.ok) throw new Error("本次依据暂时无法读取。");
        return await response.json() as Basis;
      })
      .then(result => { if (!controller.signal.aborted) { setBasis(result); setError(""); } })
      .catch((failure: unknown) => { if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : "本次依据暂时无法读取。"); });
    return () => controller.abort();
  }, [running, attempt]);

  if (running) return <p role="status" className="border-b px-5 py-3 text-xs text-muted-foreground">本次工作结束后可核对使用的依据。</p>;
  if (error) return <div role="alert" className="border-b px-5 py-3 text-xs"><p>{error}</p><Button variant="ghost" size="sm" onClick={() => setAttempt(value => value + 1)}>重试读取依据</Button></div>;
  if (!basis?.run_id) return null;
  return <details className="border-b px-5 py-3 text-xs">
    <summary className="cursor-pointer text-muted-foreground">本次依据 · {basis.references.length} 项{basis.proposals.length ? ` · ${basis.proposals.length} 条提议` : ""}</summary>
    <div className="mt-3 max-h-40 space-y-2 overflow-y-auto" aria-label="本次工作依据">
      {basis.references.length === 0 && <p className="text-muted-foreground">本次未读取已保存的职业背景或规则。</p>}
      {basis.references.map(reference => <p key={`${reference.type}-${reference.id}-${reference.version}`} className="break-words leading-5"><span>{reference.title}</span><span className="ml-2 text-muted-foreground" title={reference.version}>版本 {reference.version.slice(0, 8)}</span></p>)}
      {basis.proposals.map(proposal => <p key={proposal.id} className="break-words leading-5">提议：{proposal.title} · <Link href="/assistant" className="underline">在背景与规则核对</Link></p>)}
    </div>
  </details>;
}

export async function associateAgentSession(projectId: string | null, signal?: AbortSignal): Promise<void> {
  const response = await fetch("/api/agent/session", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ project_id: projectId }),
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { error?: { message?: string } } | null;
    throw new Error(body?.error?.message ?? "Agent 工作关联暂时无法保存。");
  }
}

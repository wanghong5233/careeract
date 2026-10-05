import { isRestrictedResponse, restrictedContentMessage } from "@/lib/privacy";

export type AgentConversation = { session_id: string; title: string; project_id: string | null; archived: boolean; version: string; created_at: string; updated_at: string; title_origin?: "default" | "manual" | "generated"; title_generation_attempted?: boolean };
export type ConversationPage = { items: AgentConversation[]; next_cursor: string | null };
export type HistoryMessage = { id: string; role: "user" | "assistant"; content: string; created_at: number; run_id: string | null; run_status: string };
export type ConversationHistory = { session: AgentConversation; messages: HistoryMessage[]; truncated: boolean; runs?: Array<{ run_id: string; status: string }> };

async function request<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(url, { ...init, cache: "no-store" });
  if (!response.ok) {
    if (response.status === 422 && await isRestrictedResponse(response)) throw new Error(restrictedContentMessage);
    const messages: Record<number, string> = { 401: "登录已失效，请重新登录。", 404: "找不到该对话或项目，请重新读取。", 409: "对话已有更新或仍在运行，请重新读取后核对；输入已保留。", 422: "请检查对话名称和项目关联。" };
    throw new Error(messages[response.status] ?? "对话服务暂不可用，请重新读取核对，草稿仍保留。");
  }
  return response.json() as Promise<T>;
}

export function readConversations(cursor?: string, signal?: AbortSignal): Promise<ConversationPage> {
  const query = new URLSearchParams({ limit: "50" });
  if (cursor) query.set("cursor", cursor);
  return request(`/api/agent/conversations?${query}`, { signal });
}

export function createConversation(id: string, title: string, projectId: string | null): Promise<AgentConversation> {
  return request("/api/agent/conversations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, title, project_id: projectId }), signal: AbortSignal.timeout(20_000) });
}

export function saveConversation(id: string, version: string, changes: { title?: string; project_id?: string | null; archived?: boolean }): Promise<AgentConversation> {
  return request(`/api/agent/conversations/${encodeURIComponent(id)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ version, ...changes }), signal: AbortSignal.timeout(20_000) });
}

export function readConversationHistory(id: string, signal?: AbortSignal): Promise<ConversationHistory> {
  return request(`/api/agent/history?${new URLSearchParams({ session_id: id, limit: "100" })}`, { signal });
}

export function generateConversationTitle(session: AgentConversation, signal?: AbortSignal): Promise<AgentConversation> {
  return request(`/api/agent/conversations/${encodeURIComponent(session.session_id)}/title`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ version: session.version }), signal });
}

export function readRuntimeModel(signal?: AbortSignal): Promise<{ id: string; connection: string }> {
  return request("/api/agent/model", { signal });
}

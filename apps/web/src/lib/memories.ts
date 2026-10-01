import { isRestrictedResponse, restrictedContentMessage } from "@/lib/privacy";

export type MemoryKind = "note" | "rule";
export type MemoryState = "candidate" | "confirmed" | "retired";

export type WorkspaceMemory = {
  id: string;
  project_id: string | null;
  kind: MemoryKind;
  state: MemoryState;
  title: string;
  content: string;
  source: string;
  version: string;
  created_at: string;
  updated_at: string;
};

type MemoryPage = { items: WorkspaceMemory[]; next_cursor: string | null };

export class MemoryRequestError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function requestMemory<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...options, cache: "no-store" });
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    throw new MemoryRequestError(0, options.method
      ? "连接中断，保存结果尚未确认。请读取核对，当前输入仍保留。"
      : "连接中断，暂时无法读取规则与笔记。");
  }
  if (!response.ok) {
    if (response.status === 422 && await isRestrictedResponse(response)) {
      throw new MemoryRequestError(response.status, restrictedContentMessage);
    }
    const messages: Record<number, string> = {
      401: "登录已失效，请重新登录。",
      403: "无法验证请求，请从工作台重试。",
      404: "找不到该规则或笔记。",
      409: "内容已有更新，请重新读取后再操作。",
      422: "请检查标题、内容和确认状态。",
      502: "保存结果尚未确认，请重新读取核对，当前输入仍保留。",
      503: "规则与笔记暂时不可用，请稍后重试。",
    };
    throw new MemoryRequestError(response.status, messages[response.status] ?? "规则与笔记暂时不可用，请稍后重试。");
  }
  try {
    return await response.json() as T;
  } catch (error) {
    if (!(error instanceof SyntaxError || error instanceof TypeError || error instanceof DOMException)) throw error;
    throw new MemoryRequestError(0, "未能完整读取规则与笔记响应，请重试。");
  }
}

export function readMemories(options: { kind?: MemoryKind; includeRetired?: boolean; cursor?: string } = {}, signal?: AbortSignal): Promise<MemoryPage> {
  const query = new URLSearchParams({ limit: "20" });
  if (options.kind) query.set("kind", options.kind);
  if (options.includeRetired) query.set("include_retired", "true");
  if (options.cursor) query.set("cursor", options.cursor);
  return requestMemory(`/api/memories?${query}`, { signal });
}

export function createMemory(
  input: { id: string; kind: MemoryKind; title: string; content: string; source?: string },
  signal?: AbortSignal,
): Promise<WorkspaceMemory> {
  return requestMemory("/api/memories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
    signal,
  });
}

export function readMemory(id: string, signal?: AbortSignal): Promise<WorkspaceMemory> {
  return requestMemory(`/api/memories/${encodeURIComponent(id)}`, { signal });
}

export function updateMemory(
  memory: WorkspaceMemory,
  input: { title?: string; content?: string },
  signal?: AbortSignal,
): Promise<WorkspaceMemory> {
  return requestMemory(`/api/memories/${encodeURIComponent(memory.id)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...input, version: memory.version }),
    signal,
  });
}

export function confirmMemory(memory: WorkspaceMemory, signal?: AbortSignal): Promise<WorkspaceMemory> {
  return requestMemory(`/api/memories/${encodeURIComponent(memory.id)}/confirm`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version: memory.version }),
    signal,
  });
}

export function retireMemory(memory: WorkspaceMemory, signal?: AbortSignal): Promise<WorkspaceMemory> {
  return requestMemory(`/api/memories/${encodeURIComponent(memory.id)}/retire`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version: memory.version }),
    signal,
  });
}

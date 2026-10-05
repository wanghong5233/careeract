import { isRestrictedResponse, restrictedContentMessage } from "@/lib/privacy";

export type MaterialVersion = {
  id: string;
  material_id: string;
  number: number;
  body: string;
  source: "seed" | "user" | "agent";
  created_at: string;
  references: MaterialReference[];
};

export type MaterialReference = { type: string; id?: string; title: string; version: string };

export type MaterialProposal = {
  id: string;
  material_id: string;
  base_version_id: string;
  proposed_body: string;
  rationale: string;
  state: "pending" | "accepted" | "rejected";
  created_at: string;
  resolved_at: string | null;
  diff: string[];
  base_body: string;
  base_number: number;
  references: MaterialReference[];
  stale: boolean;
  changes: Array<{ id: string; start: number; end: number; original: string; replacement: string; state: "pending" | "accepted" | "rejected"; revisions?: Array<{ replacement: string; review_version: string; request_id: string }> }>;
  review_version: string | null;
  review_body: string;
};

export type CareerMaterial = {
  id: string;
  project_id: string | null;
  title: string;
  state: "active" | "archived";
  current_version_id: string;
  version: string;
  created_at: string;
  updated_at: string;
  current_version: MaterialVersion | null;
  versions: MaterialVersion[];
  proposals: MaterialProposal[];
};

export class MaterialRequestError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function requestMaterial<T>(path: string, options: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, { ...options, cache: "no-store" });
  } catch (error) {
    if (!(error instanceof TypeError || error instanceof DOMException)) throw error;
    throw new MaterialRequestError(0, options.method ? "连接中断，尚不能确认材料是否保存。" : "连接中断，暂时无法读取材料。");
  }
  if (!response.ok) {
    if (response.status === 422 && await isRestrictedResponse(response)) throw new MaterialRequestError(response.status, restrictedContentMessage);
    const messages: Record<number, string> = {
      401: "登录已失效，请重新登录。",
      403: "无法验证请求，请从 CareerAct Agent 重试。",
      404: "找不到该材料，或你没有访问权限。",
      409: "材料已有更新，请读取最新版本后再操作。",
      422: "请检查材料正文、标题和版本。",
      503: "材料服务暂不可用，请稍后重试。",
    };
    throw new MaterialRequestError(response.status, messages[response.status] ?? "材料服务暂不可用，请重新读取核对。");
  }
  try { return await response.json() as T; }
  catch (error) {
    if (!(error instanceof SyntaxError || error instanceof TypeError || error instanceof DOMException)) throw error;
    throw new MaterialRequestError(0, "响应未完整读取，请重新读取材料核对。");
  }
}

export function readMaterials(cursor?: string, signal?: AbortSignal): Promise<{ items: CareerMaterial[]; next_cursor: string | null }> {
  const query = cursor ? `?cursor=${encodeURIComponent(cursor)}` : "";
  return requestMaterial(`/api/materials${query}`, { signal });
}

export function readMaterial(id: string, signal?: AbortSignal): Promise<CareerMaterial> {
  return requestMaterial(`/api/materials/${encodeURIComponent(id)}`, { signal });
}

export function saveMaterialVersion(id: string, input: { base_version_id: string; body: string }, signal?: AbortSignal): Promise<CareerMaterial> {
  return requestMaterial(`/api/materials/${encodeURIComponent(id)}/versions`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input), signal,
  });
}

export function resolveMaterialProposal(id: string, proposalId: string, input: { state: "accepted" | "rejected"; change_ids?: string[]; version?: string; replacement?: string }, signal?: AbortSignal): Promise<CareerMaterial> {
  return requestMaterial(`/api/materials/${encodeURIComponent(id)}/proposals/${encodeURIComponent(proposalId)}/resolve`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(input), signal,
  });
}

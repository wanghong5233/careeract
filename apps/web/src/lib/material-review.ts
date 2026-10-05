import type { MaterialProposal } from "@/lib/materials";

export function pendingSelection(proposal: MaterialProposal, selection?: string[]) {
  const pending = proposal.changes.filter(change => change.state === "pending").map(change => change.id);
  return selection === undefined ? pending : pending.filter(identifier => selection.includes(identifier));
}

export function toggleSelection(proposal: MaterialProposal, selection: string[] | undefined, identifier: string, checked: boolean) {
  const current = pendingSelection(proposal, selection);
  return checked ? Array.from(new Set([...current, identifier])) : current.filter(item => item !== identifier);
}

export function rewritePrompt(materialId: string, proposal: MaterialProposal, changeId: string) {
  return `请用 read_material 读取材料 ${materialId} 的当前版本与待审修改。只改写提议 ${proposal.id} 中的 ${changeId}，不要创建整份新提议或接受修改。先核对当前正文、修改块和 review_version；用 propose_material_edit 的 proposal_id、change_id、review_version 参数保存该处待审替代文本，proposed_body 只传替代文本。其他已接受、拒绝和待审内容必须保留。不要添加未提供的职业事实。我的反馈：\n`;
}

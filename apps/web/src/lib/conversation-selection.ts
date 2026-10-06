export function selectConversationRange(order: string[], selected: string[], anchor: string | null, target: string, range: boolean, additive: boolean): string[] {
  const available = selected.filter(id => order.includes(id));
  const start = anchor ? order.indexOf(anchor) : -1;
  const end = order.indexOf(target);
  if (end < 0) return available;
  if (range && start >= 0) {
    const span = order.slice(Math.min(start, end), Math.max(start, end) + 1);
    return additive ? [...new Set([...available, ...span])] : span;
  }
  return available.includes(target) ? available.filter(id => id !== target) : [...available, target];
}

export async function deleteConversationSelection<Item extends { id: string; version?: string }>(items: Item[], remove: (id: string, version?: string) => Promise<void>) {
  for (const [index, item] of items.entries()) {
    try { await remove(item.id, item.version); }
    catch (error) { return { remaining: items.slice(index), deleted: index, error }; }
  }
  return { remaining: [] as Item[], deleted: items.length, error: null };
}

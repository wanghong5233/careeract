export function formatRunDuration(seconds: unknown): string | null {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return null;
  const total = Math.floor(seconds);
  return total < 60 ? `${total}秒` : `${Math.floor(total / 60)}分${total % 60}秒`;
}

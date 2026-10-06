export function formatRunDuration(seconds: unknown): string | null {
  if (typeof seconds !== "number" || !Number.isFinite(seconds) || seconds < 0) return null;
  const total = Math.floor(seconds);
  return total < 60 ? `${total}秒` : `${Math.floor(total / 60)}分${total % 60}秒`;
}

export function formatMessageTimestamp(timestamp: unknown, timeZone?: string): { dateTime: string; label: string; title: string } | null {
  if (typeof timestamp !== "number" || !Number.isFinite(timestamp) || timestamp <= 0) return null;
  const date = new Date(timestamp);
  if (!Number.isFinite(date.getTime())) return null;
  const weekday = new Intl.DateTimeFormat("zh-CN", { weekday: "long", timeZone }).format(date);
  const clock = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hourCycle: "h23", timeZone }).format(date);
  return {
    dateTime: date.toISOString(),
    label: `${weekday} ${clock}`,
    title: new Intl.DateTimeFormat("zh-CN", { dateStyle: "full", timeStyle: "short", timeZone }).format(date),
  };
}

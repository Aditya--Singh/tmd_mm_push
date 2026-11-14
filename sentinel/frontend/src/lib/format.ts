const IST = "Asia/Kolkata";

export function fmtDate(iso?: string | null, withTime = false): string {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", {
    timeZone: IST,
    day: "2-digit",
    month: "short",
    year: "numeric",
    ...(withTime ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}),
  });
}

export function fmtTime(iso?: string | null): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleTimeString("en-IN", { timeZone: IST, hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

export function relTime(iso?: string | null): string {
  if (!iso) return "never";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  const future = diff < 0;
  const s = Math.abs(diff);
  const v = s < 45 ? "moments" : s < 3600 ? `${Math.round(s / 60)} min` : s < 86400 ? `${Math.round(s / 3600)} h` : `${Math.round(s / 86400)} d`;
  if (v === "moments") return future ? "in a moment" : "just now";
  return future ? `in ${v}` : `${v} ago`;
}

export function fmtMs(ms?: number | null): string {
  if (ms == null) return "–";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`;
}

export function pct(v?: number | null): string {
  return v == null ? "–" : `${Math.round(v * 100)}%`;
}

const SOURCE_LABELS: Record<string, string> = {
  notification: "Notification",
  press_release: "Press release",
  master_circular: "Master circular",
  master_direction: "Master direction",
};
export const sourceLabel = (s: string) => SOURCE_LABELS[s] ?? s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

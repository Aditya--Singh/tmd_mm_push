// Thin fetch wrapper + Server-Sent-Events reader that can send the Authorization header
// (the browser's EventSource cannot), used for both chat streaming and the live activity feed.

const TOKEN_KEY = "sentinel.token";

export const getToken = () => {
  try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
};
export const setToken = (t: string | null) => {
  try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ }
};

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401) {
    setToken(null);
    window.dispatchEvent(new Event("sentinel:unauthorized"));
  }
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = body.detail.map((d: { msg: string }) => d.msg).join("; ");
    } catch { /* not json */ }
    throw new ApiError(res.status, msg);
  }
  const type = res.headers.get("content-type") || "";
  return (type.includes("application/json") ? res.json() : res.text()) as Promise<T>;
}

function headers(json = true): HeadersInit {
  const h: Record<string, string> = {};
  if (json) h["Content-Type"] = "application/json";
  const t = getToken();
  if (t) h.Authorization = `Bearer ${t}`;
  return h;
}

export const api = {
  get: <T,>(path: string) => fetch(path, { headers: headers(false) }).then((r) => handle<T>(r)),
  post: <T,>(path: string, body?: unknown) =>
    fetch(path, { method: "POST", headers: headers(), body: body === undefined ? undefined : JSON.stringify(body) }).then((r) => handle<T>(r)),
  put: <T,>(path: string, body: unknown) =>
    fetch(path, { method: "PUT", headers: headers(), body: JSON.stringify(body) }).then((r) => handle<T>(r)),
  patch: <T,>(path: string, body: unknown) =>
    fetch(path, { method: "PATCH", headers: headers(), body: JSON.stringify(body) }).then((r) => handle<T>(r)),
  del: <T,>(path: string) => fetch(path, { method: "DELETE", headers: headers(false) }).then((r) => handle<T>(r)),
  download: async (path: string, filename: string) => {
    const res = await fetch(path, { headers: headers(false) });
    if (!res.ok) throw new ApiError(res.status, "Download failed");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  },
};

/** POST (or GET) and read a text/event-stream response, calling onEvent for every `data:` JSON payload. */
export async function streamSSE(
  path: string,
  opts: { body?: unknown; method?: "GET" | "POST"; signal?: AbortSignal; onEvent: (ev: any) => void },
) {
  const res = await fetch(path, {
    method: opts.method ?? (opts.body ? "POST" : "GET"),
    headers: { ...headers(!!opts.body), Accept: "text/event-stream" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    signal: opts.signal,
  });
  if (!res.ok || !res.body) await handle(res);
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      for (const line of block.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        try { opts.onEvent(JSON.parse(line.slice(6))); } catch { /* ignore partial */ }
      }
    }
  }
}

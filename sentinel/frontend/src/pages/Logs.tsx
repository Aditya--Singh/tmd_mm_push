import clsx from "clsx";
import { Pause, Play } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { PageHeader, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { fmtDate } from "../lib/format";
import { useLiveListener } from "../lib/live";

type Log = { ts: string; level: string; logger: string; message: string; trace_id?: string | null; agent?: string | null; [k: string]: any };
const LEVEL_TONE: Record<string, string> = { ERROR: "text-maroon", CRITICAL: "text-maroon", WARNING: "text-gold-text", INFO: "text-slate", DEBUG: "text-faint" };
const BASE = new Set(["ts", "level", "logger", "message", "trace_id", "span_id", "agent", "type", "_at"]);

export default function Logs() {
  const [level, setLevel] = useState("INFO");
  const [q, setQ] = useState("");
  const [logs, setLogs] = useState<Log[] | null>(null);
  const [live, setLive] = useState(true);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams({ limit: "400", level });
      if (q) p.set("q", q);
      api.get<Log[]>(`/api/logs?${p}`).then(setLogs).catch((e) => toast.error(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [level, q]);

  useLiveListener((ev) => {
    if (!live || ev.type !== "log") return;
    const order: Record<string, number> = { DEBUG: 10, INFO: 20, WARNING: 30, ERROR: 40, CRITICAL: 50 };
    if ((order[ev.level] ?? 0) < (order[level] ?? 0)) return;
    if (q && !JSON.stringify(ev).toLowerCase().includes(q.toLowerCase())) return;
    setLogs((prev) => [ev as unknown as Log, ...(prev ?? [])].slice(0, 600));
  }, [live, level, q]);

  return (
    <div>
      <PageHeader
        title="Logs"
        sub="Structured JSON logs. Each line carries the trace and agent that produced it, so you can jump from a log line to the full agent trace."
        actions={<button className="btn" onClick={() => setLive(!live)}>{live ? <><Pause size={14} /> Pause live tail</> : <><Play size={14} /> Resume live tail</>}</button>}
      />
      <div className="flex flex-wrap gap-2 px-5 py-3 md:px-8">
        <select className="select w-auto" value={level} onChange={(e) => setLevel(e.target.value)} aria-label="Minimum level">
          <option value="DEBUG">Debug and above</option><option value="INFO">Info and above</option><option value="WARNING">Warnings and errors</option><option value="ERROR">Errors only</option>
        </select>
        <input className="input max-w-sm" placeholder="Filter by text, agent or trace id" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <div className="mx-5 mb-8 overflow-x-auto rounded-lg border border-line bg-surface md:mx-8">
        {!logs ? <div className="p-6"><Spinner /></div> : (
          <table className="data min-w-[820px] font-mono text-[12px]">
            <thead><tr><th className="w-[150px]">Time (IST)</th><th className="w-[72px]">Level</th><th className="w-[110px]">Agent</th><th>Message</th><th className="w-[110px]">Trace</th></tr></thead>
            <tbody>
              {logs.map((l, i) => {
                const extra = Object.fromEntries(Object.entries(l).filter(([k]) => !BASE.has(k)));
                return (
                  <tr key={i} className="clickable" onClick={() => setOpen(open === i ? null : i)}>
                    <td className="tabular-nums text-muted">{fmtDate(l.ts, true)}</td>
                    <td className={clsx("font-medium", LEVEL_TONE[l.level])}>{l.level}</td>
                    <td className="text-muted">{l.agent || l.logger.replace("sentinel.", "")}</td>
                    <td>
                      <span className="text-text">{l.message}</span>
                      {open === i ? <pre className="json mt-1 text-muted">{JSON.stringify(extra, null, 2)}</pre> : Object.keys(extra).length > 0 && <span className="text-faint"> {JSON.stringify(extra).slice(0, 110)}</span>}
                    </td>
                    <td>{l.trace_id ? <Link onClick={(e) => e.stopPropagation()} className="text-link hover:underline" to={`/traces?id=${l.trace_id}`}>{l.trace_id.slice(0, 8)}</Link> : <span className="text-faint">–</span>}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

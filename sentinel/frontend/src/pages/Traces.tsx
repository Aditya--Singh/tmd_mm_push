import clsx from "clsx";
import { Fragment, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { Empty, JsonView, PageHeader, Spinner, StatusTag, agentColor } from "../components/ui";
import { api } from "../lib/api";
import { fmtDate, fmtMs, fmtTime } from "../lib/format";
import { useLiveListener } from "../lib/live";
import type { SpanRow, TraceDetail, TraceRow } from "../lib/types";

const AGENTS = ["Watcher", "Ingestion", "Summarizer", "Indexer", "Notifier", "Router", "Retriever", "Answer", "Verifier", "Memory", "Briefing", "Resolver", "LLM"];

export default function Traces() {
  const [params, setParams] = useSearchParams();
  const [kind, setKind] = useState("");
  const [status, setStatus] = useState("");
  const [agent, setAgent] = useState(params.get("agent") ?? "");
  const [rows, setRows] = useState<TraceRow[] | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(params.get("id"));
  const [detail, setDetail] = useState<TraceDetail | null>(null);
  const [span, setSpan] = useState<SpanRow | null>(null);

  const load = () => {
    const p = new URLSearchParams({ limit: "80" });
    if (kind) p.set("kind", kind);
    if (status) p.set("status", status);
    if (agent) p.set("agent", agent);
    api.get<{ items: TraceRow[] }>(`/api/traces?${p}`).then((r) => {
      setRows(r.items);
      if (!selectedId && r.items[0]) setSelectedId(r.items[0].id);
    }).catch((e) => toast.error(e.message));
  };
  useEffect(load, [kind, status, agent]);
  useLiveListener((ev) => {
    if (ev.type === "trace" && ev.phase === "end") {
      load();
      if (ev.trace_id === selectedId) loadDetail(ev.trace_id);
    }
  }, [kind, status, agent, selectedId]);

  const loadDetail = (id: string) =>
    api.get<TraceDetail>(`/api/traces/${id}`).then((t) => {
      setDetail(t);
      setSpan((prev) => (prev ? t.spans.find((s) => s.id === prev.id) ?? null : null));
    }).catch((e) => toast.error(e.message));

  useEffect(() => {
    if (!selectedId) return;
    setSpan(null);
    loadDetail(selectedId);
    params.set("id", selectedId);
    setParams(params, { replace: true });
  }, [selectedId]);

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Agent traces" sub="Every chat turn, RBI check and e-mail, step by step: inputs, outputs, model, tokens and timing." />
      <div className="flex flex-wrap gap-2 px-5 py-3 md:px-8">
        <select className="select w-auto" value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Kind">
          <option value="">All kinds</option><option value="chat">Chat</option><option value="sync">RBI check</option><option value="email">E-mail</option><option value="system">System</option>
        </select>
        <select className="select w-auto" value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status">
          <option value="">Any status</option><option value="ok">Succeeded</option><option value="error">Failed</option><option value="running">Running</option><option value="cancelled">Cancelled</option>
        </select>
        <select className="select w-auto" value={agent} onChange={(e) => setAgent(e.target.value)} aria-label="Agent">
          <option value="">Any agent</option>{AGENTS.map((a) => <option key={a}>{a}</option>)}
        </select>
      </div>
      <div className="grid min-h-0 flex-1 gap-0 border-t border-line lg:grid-cols-[360px_minmax(0,1fr)]">
        <div className="min-h-0 overflow-y-auto border-r border-line bg-surface max-lg:max-h-[300px]">
          {!rows ? <div className="p-6 text-muted"><Spinner /></div> : rows.length === 0 ? <Empty title="No traces yet">Ask the assistant a question or run an RBI check.</Empty> : (
            <ul>
              {rows.map((t) => (
                <li key={t.id}>
                  <button onClick={() => setSelectedId(t.id)} className={clsx("w-full border-b border-line px-4 py-2.5 text-left", selectedId === t.id ? "bg-ink-soft" : "hover:bg-surface-2")}>
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11.5px] text-muted">{kindLabel(t.kind)} · {fmtDate(t.started_at, true)}</span>
                      <StatusTag status={t.status} />
                    </div>
                    <div className="mt-0.5 truncate text-[13.5px] text-text">{t.name}</div>
                    <div className="text-[11.5px] tabular-nums text-faint">{fmtMs(t.duration_ms)} · {t.spans} steps{t.tokens_in + t.tokens_out > 0 ? ` · ${t.tokens_in + t.tokens_out} tokens` : ""}{t.actor ? ` · ${t.actor}` : ""}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div className="min-h-0 overflow-y-auto px-5 py-5 md:px-7">
          {!detail ? <div className="text-muted">Select a trace.</div> : <TraceView t={detail} span={span} onSpan={setSpan} />}
        </div>
      </div>
    </div>
  );
}

const kindLabel = (k: string) => ({ chat: "Chat", sync: "RBI check", email: "E-mail", system: "System" } as Record<string, string>)[k] ?? k;

function TraceView({ t, span, onSpan }: { t: TraceDetail; span: SpanRow | null; onSpan: (s: SpanRow) => void }) {
  const start = new Date(t.started_at).getTime();
  const total = Math.max(t.duration_ms ?? 0, ...t.spans.map((s) => new Date(s.started_at).getTime() - start + (s.duration_ms ?? 0)), 1);
  const depth = useMemo(() => {
    const byId = Object.fromEntries(t.spans.map((s) => [s.id, s]));
    const d: Record<string, number> = {};
    const get = (s: SpanRow): number => (d[s.id] ??= s.parent_id && byId[s.parent_id] ? get(byId[s.parent_id]) + 1 : 0);
    t.spans.forEach(get);
    return d;
  }, [t]);
  const llm = t.spans.filter((s) => s.agent === "LLM");

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[12px] text-muted">{kindLabel(t.kind)} trace · {t.id}</div>
          <h2 className="mt-0.5 text-[1.35rem] leading-snug">{t.name}</h2>
        </div>
        <StatusTag status={t.status} />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-[13px] sm:grid-cols-4">
        <div><dt className="text-muted">Started</dt><dd className="tabular-nums">{fmtDate(t.started_at, true)}</dd></div>
        <div><dt className="text-muted">Duration</dt><dd className="tabular-nums">{fmtMs(t.duration_ms)}</dd></div>
        <div><dt className="text-muted">Model calls</dt><dd className="tabular-nums">{llm.length} · {t.tokens_in} in / {t.tokens_out} out tokens</dd></div>
        <div><dt className="text-muted">Initiated by</dt><dd className="truncate">{t.actor || "system"}</dd></div>
      </dl>
      {t.error && <div className="mt-3 rounded-md border border-maroon/30 bg-maroon-soft px-3 py-2 text-[13px] text-maroon">{t.error}</div>}

      <h3 className="mt-6 text-[1.05rem]">Timeline</h3>
      <div className="mt-2 overflow-x-auto rounded-lg border border-line bg-surface">
        <div className="min-w-[560px]">
          {t.spans.map((s) => {
            const off = ((new Date(s.started_at).getTime() - start) / total) * 100;
            const w = Math.max(((s.duration_ms ?? 0) / total) * 100, 0.6);
            return (
              <button key={s.id} onClick={() => onSpan(s)} className={clsx("grid w-full grid-cols-[230px_1fr_70px] items-center gap-3 border-b border-line px-3 py-1.5 text-left text-[12.5px] last:border-0", span?.id === s.id ? "bg-gold-soft" : "hover:bg-surface-2")}>
                <span className="truncate" style={{ paddingLeft: depth[s.id] * 14 }}>
                  <span className="font-medium" style={{ color: agentColor(s.agent) }}>{s.agent}</span>{" "}
                  <span className="text-muted">{s.name}</span>
                </span>
                <span className="relative h-3 rounded bg-surface-2">
                  <span className={clsx("absolute top-0 h-3 rounded", s.status === "error" && "outline outline-1 outline-maroon")} style={{ left: `${off}%`, width: `${Math.min(w, 100 - off)}%`, background: s.status === "error" ? "var(--maroon)" : agentColor(s.agent), opacity: s.status === "running" ? 0.45 : 0.9 }} />
                </span>
                <span className="text-right tabular-nums text-muted">{fmtMs(s.duration_ms)}</span>
              </button>
            );
          })}
        </div>
      </div>

      {span ? (
        <section className="mt-6">
          <div className="flex items-center gap-2">
            <h3 className="text-[1.05rem]"><span style={{ color: agentColor(span.agent) }}>{span.agent}</span> · {span.name}</h3>
            <StatusTag status={span.status} />
          </div>
          <div className="mt-1 text-[12px] text-faint">{fmtTime(span.started_at)} → {fmtTime(span.ended_at)} · {fmtMs(span.duration_ms)}</div>
          {span.error && <div className="mt-2 rounded-md border border-maroon/30 bg-maroon-soft px-3 py-2 text-[13px] text-maroon">{span.error}</div>}
          {span.attributes && Object.keys(span.attributes).length > 0 && (
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-0.5 text-[12.5px]">
              {Object.entries(span.attributes).map(([k, v]) => (<Fragment key={k}><dt className="text-muted">{k}</dt><dd className="break-all">{typeof v === "object" ? JSON.stringify(v) : String(v)}</dd></Fragment>))}
            </dl>
          )}
          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <div><div className="label mb-1">Input</div><JsonView value={span.input} /></div>
            <div><div className="label mb-1">Output</div><JsonView value={span.output} /></div>
          </div>
        </section>
      ) : (
        <section className="mt-6 grid gap-4 xl:grid-cols-2">
          <div><div className="label mb-1">Trace input</div><JsonView value={t.input} /></div>
          <div><div className="label mb-1">Trace output</div><JsonView value={t.output} /></div>
        </section>
      )}

      {t.audit.length > 0 && (
        <section className="mt-6">
          <h3 className="text-[1.05rem]">Audit events in this trace</h3>
          <ul className="mt-2 text-[12.5px]">
            {t.audit.map((a, i) => <li key={i} className="border-b border-line py-1.5"><span className="tabular-nums text-faint">{fmtTime(a.ts)}</span> · <b className="font-medium">{a.action}</b> by {a.actor} {a.resource && <span className="text-muted">on {a.resource}</span>}</li>)}
          </ul>
        </section>
      )}
    </div>
  );
}

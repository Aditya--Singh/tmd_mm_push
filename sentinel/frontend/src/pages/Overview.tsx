import clsx from "clsx";
import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis } from "recharts";
import { toast } from "sonner";
import { Applicability, Empty, PageHeader, PriorityTag, Spinner, StatusTag, agentColor } from "../components/ui";
import { api } from "../lib/api";
import { fmtDate, fmtMs, pct, relTime, sourceLabel } from "../lib/format";
import { useLive, useLiveListener } from "../lib/live";
import type { CircularBrief } from "../lib/types";

interface Dash {
  kpis: Record<string, number | null>;
  agents: { name: string; description: string; runs_24h: number; errors_24h: number; p50_ms: number | null; last_run: string | null; health: string }[];
  series: { date: string; count: number }[];
  latest: CircularBrief[];
  sync: { running: boolean; last_finished: string | null; last_result: any; last_trace_id: string | null };
  coverage: { source: string; url: string; indexed: number; last_ok: boolean | null; last_entries: number | null; last_error: string | null; waiting: number; baselined: boolean }[];
  system: { llm: { provider: string; model: string; healthy: boolean | null; last_error: string | null }; embedding_model: string; embedding_fallback: string | null };
}

export default function Overview() {
  const [d, setD] = useState<Dash | null>(null);
  const [next, setNext] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);
  const nav = useNavigate();

  const load = useCallback(async () => {
    const [dash, sched] = await Promise.all([api.get<Dash>("/api/dashboard"), api.get<{ next_run: string | null }>("/api/schedule")]);
    setD(dash);
    setNext(sched.next_run);
    setSyncing(dash.sync.running);
  }, []);

  useEffect(() => { load().catch((e) => toast.error(e.message)); }, [load]);
  useLiveListener((ev) => {
    if (ev.type === "sync" && ev.phase === "end") {
      setSyncing(false);
      load();
      const r = ev.result || {};
      if (r.status === "error") toast.error(`RBI check failed: ${r.error}`);
      else toast.success(r.ingested ? `${r.ingested} new publication${r.ingested > 1 ? "s" : ""} indexed` : "RBI checked — nothing new");
    }
    if (ev.type === "sync" && ev.phase === "start") setSyncing(true);
  }, [load]);

  const syncNow = async () => {
    setSyncing(true);
    try {
      await api.post("/api/sync");
    } catch (e: any) {
      toast.error(e.message);
      setSyncing(false);
    }
  };

  if (!d) return <div className="grid h-64 place-items-center text-muted"><Spinner /></div>;
  const k = d.kpis;
  const lastFeeds = d.sync.last_result?.feeds as { source: string; ok: boolean; error?: string }[] | undefined;
  const feedErrors = lastFeeds?.filter((f) => !f.ok) ?? [];

  return (
    <div>
      <PageHeader
        title="Overview"
        sub={
          <>
            {syncing ? "Checking the RBI website now…" : <>Last checked {relTime(d.sync.last_finished)}</>}
            {next && !syncing && <> · next check {relTime(next)}</>}
          </>
        }
        actions={
          <button className="btn btn-primary" onClick={syncNow} disabled={syncing}>
            {syncing ? <Spinner /> : <RefreshCw size={15} />} Check RBI now
          </button>
        }
      />

      {feedErrors.length > 0 && (
        <div className="mx-5 mt-4 rounded-md border border-maroon/30 bg-maroon-soft px-4 py-2.5 text-[13px] text-maroon md:mx-8">
          The last check could not reach {feedErrors.map((f) => sourceLabel(f.source)).join(" and ")}: {feedErrors[0].error}. Sentinel will retry on schedule.
        </div>
      )}
      {d.system.embedding_fallback && (
        <div className="mx-5 mt-4 rounded-md border border-gold/40 bg-gold-soft px-4 py-2.5 text-[13px] text-gold-text md:mx-8">
          Search is running on the built-in keyword-hash embedder because the configured embedding model could not load. Answers still work, but
          semantic matching is weaker. See Settings → System.
        </div>
      )}

      {/* KPI ledger: one strip, divided like a register rather than a grid of cards */}
      <div className="mx-5 mt-5 grid grid-cols-2 overflow-hidden rounded-lg border border-line bg-surface sm:grid-cols-3 md:mx-8 xl:grid-cols-6">
        {[
          ["Publications indexed", k.indexed, `${k.chunks ?? 0} searchable passages`],
          ["New in 7 days", k.new_7d, k.revised_7d ? `${k.revised_7d} revised by RBI` : null],
          ["High priority, 7 days", k.high_priority_7d, null, (k.high_priority_7d ?? 0) > 0],
          ["Master circulars and directions", k.master_documents, "consolidated instructions"],
          ["AI summaries written", k.ai_summarised, `of ${(k.indexed ?? 0) - (k.superseded ?? 0)} current documents`],
          ["Answer satisfaction", pct(k.feedback_positive_rate as number | null), `${k.feedback_count ?? 0} ratings`],
        ].map(([label, value, hint, alert], i) => (
          <div key={String(label)} className={clsx("border-line px-4 py-3.5", i > 0 && "border-l", i >= 2 && "max-sm:border-t", i >= 3 && "max-xl:border-t")}>
            <div className="text-[12px] text-muted">{label}</div>
            <div className={clsx("mt-0.5 font-serif text-[1.75rem] leading-tight tabular-nums", alert ? "text-maroon" : "text-text")}>{value ?? 0}</div>
            {hint && <div className="text-[11.5px] text-faint">{hint}</div>}
          </div>
        ))}
      </div>

      <div className="grid gap-6 px-5 py-6 md:px-8 xl:grid-cols-[1.45fr_1fr]">
        <section className="panel min-w-0">
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <h2 className="text-[1.15rem]">Latest from the RBI</h2>
            <Link to="/circulars" className="text-[13px] text-link hover:underline">All circulars</Link>
          </div>
          {d.latest.length === 0 ? (
            <Empty title="Nothing indexed yet" action={<button className="btn" onClick={syncNow}>Check RBI now</button>}>
              The first check builds the baseline quietly; alerts start with the next new publication.
            </Empty>
          ) : (
            <ul>
              {d.latest.map((c) => (
                <li key={c.id}>
                  <button onClick={() => nav(`/circulars/${c.id}`)} className="grid w-full grid-cols-[64px_1fr] gap-3 border-b border-line px-4 py-3 text-left last:border-0 hover:bg-surface-2">
                    <div className="pt-0.5 text-[12px] leading-tight text-muted tabular-nums">{fmtDate(c.published_at).replace(/ \d{4}$/, "")}</div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <PriorityTag value={c.priority} />
                        <Applicability value={c.applicability} />
                        <span className="text-[12px] text-faint">{sourceLabel(c.source)}</span>
                      </div>
                      <div className="mt-1 font-serif text-[15.5px] leading-snug text-text">{c.title}</div>
                      {c.summary?.summary && <p className="mt-1 line-clamp-2 text-[13px] text-muted">{c.summary.summary}</p>}
                      {c.rbi_ref && <div className="mt-1 text-[12px] text-faint">{c.rbi_ref}{c.dept_ref ? ` · ${c.dept_ref}` : ""}</div>}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
          <div className="border-t border-line px-4 pb-2 pt-3">
            <div className="text-[12px] text-muted">Publications per day, last 30 days</div>
            <div className="h-[86px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={d.series} margin={{ top: 6, right: 0, left: 0, bottom: 0 }}>
                  <XAxis dataKey="date" hide />
                  <Tooltip cursor={{ fill: "var(--ink-soft)" }} contentStyle={{ background: "var(--surface)", border: "1px solid var(--line)", borderRadius: 6, fontSize: 12 }}
                    labelFormatter={(v) => fmtDate(String(v))} formatter={(v) => [v, "Publications"]} />
                  <Bar dataKey="count" fill="var(--brand)" radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </section>

        <div className="min-w-0 space-y-6">
          <Coverage rows={d.coverage} />
          <section className="panel">
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <h2 className="text-[1.15rem]">Agents, last 24 hours</h2>
              <Link to="/traces" className="text-[13px] text-link hover:underline">Traces</Link>
            </div>
            <table className="data">
              <thead><tr><th>Agent</th><th className="text-right">Runs</th><th className="text-right">Median</th><th>Last run</th></tr></thead>
              <tbody>
                {d.agents.map((a) => (
                  <tr key={a.name} className="clickable" onClick={() => nav(`/traces?agent=${a.name}`)} title={a.description}>
                    <td>
                      <span className="inline-flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full" style={{ background: a.health === "degraded" ? "var(--maroon)" : a.health === "idle" ? "var(--line-strong)" : agentColor(a.name) }} />
                        {a.name}
                        {a.errors_24h > 0 && <span className="text-[11.5px] text-maroon">{a.errors_24h} failed</span>}
                      </span>
                    </td>
                    <td className="text-right tabular-nums">{a.runs_24h}</td>
                    <td className="text-right tabular-nums text-muted">{fmtMs(a.p50_ms)}</td>
                    <td className="text-muted">{relTime(a.last_run)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="border-t border-line px-4 py-2.5 text-[12px] text-muted">
              Model: <span className="text-text">{d.system.llm.provider === "none" ? "none (rules and extractive mode)" : `${d.system.llm.model} via ${d.system.llm.provider}`}</span>
              {d.system.llm.healthy === false && <span className="text-maroon"> · last call failed</span>}
              <br />Embeddings: <span className="text-text">{d.system.embedding_model}</span>
            </div>
          </section>
          <LiveFeed />
        </div>
      </div>
    </div>
  );
}

function Coverage({ rows }: { rows: Dash["coverage"] }) {
  const nav = useNavigate();
  return (
    <section className="panel">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-[1.15rem]">Sources covered</h2>
      </div>
      <table className="data">
        <thead><tr><th>RBI source</th><th className="text-right">Indexed</th><th>Last check</th></tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.source} className="clickable" onClick={() => nav(`/circulars?source=${r.source}`)} title={r.url}>
              <td>
                {sourceLabel(r.source)}s
                {!r.baselined && r.last_ok && <div className="text-[11.5px] text-gold-text">first-time load{r.waiting ? `, ${r.waiting} still to read` : ""} (no alerts yet)</div>}
              </td>
              <td className="text-right tabular-nums">{r.indexed}</td>
              <td className="text-[12.5px]">
                {r.last_ok == null ? <span className="text-faint">not checked yet</span>
                  : r.last_ok ? <span className="text-ok">read {r.last_entries} entries</span>
                  : <span className="text-maroon" title={r.last_error ?? ""}>failed</span>}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function LiveFeed() {
  const { events } = useLive();
  const shown = events.filter((e) => e.type === "span" || e.type === "trace" || e.type === "audit").slice(-14).reverse();
  return (
    <section className="panel">
      <div className="border-b border-line px-4 py-3">
        <h2 className="text-[1.15rem]">Live activity</h2>
      </div>
      {shown.length === 0 ? (
        <p className="px-4 py-6 text-[13px] text-muted">Agent activity will stream here as it happens.</p>
      ) : (
        <ul className="max-h-[330px] overflow-y-auto px-4 py-2 text-[12.5px]">
          {shown.map((e, i) => (
            <li key={i} className="flex items-start gap-2 border-b border-line py-1.5 last:border-0">
              <span className="mt-1.5 h-1.5 w-1.5 flex-none rounded-full" style={{ background: e.type === "audit" ? "var(--gold)" : agentColor(e.agent || e.kind || "") }} />
              <div className="min-w-0 flex-1">
                {e.type === "span" && (
                  <span><b className="font-medium" style={{ color: agentColor(e.agent) }}>{e.agent}</b> {e.phase === "start" ? "started" : "finished"} {e.name}{e.phase === "end" && <> · {fmtMs(e.duration_ms)}</>}</span>
                )}
                {e.type === "trace" && (<span>{e.phase === "start" ? "Started" : "Completed"} {e.kind}: {e.name}{e.status && e.status !== "ok" && <> · <StatusTag status={e.status} /></>}</span>)}
                {e.type === "audit" && (<span className="text-muted">Audit: {e.action} by {e.actor}</span>)}
              </div>
              <span className="flex-none text-faint">{e._at ? new Date(e._at).toLocaleTimeString("en-IN", { hour12: false }) : ""}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

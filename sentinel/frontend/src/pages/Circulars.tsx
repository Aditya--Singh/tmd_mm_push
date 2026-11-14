import { ArrowLeft, ExternalLink, FileText, Mail, MessageSquareText, RotateCcw, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { toast } from "sonner";
import { Applicability, Empty, PageHeader, PriorityTag, Spinner, StatusTag, Tag } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useMeta } from "../lib/meta";
import { fmtDate, relTime, sourceLabel } from "../lib/format";
import type { CircularBrief, CircularDetail } from "../lib/types";

const FY_OPTIONS = (() => {
  const now = new Date();
  const start = now.getMonth() >= 3 ? now.getFullYear() : now.getFullYear() - 1;
  return Array.from({ length: 25 }, (_, i) => `${start - i}-${start - i + 1}`);
})();

export function CircularList() {
  const [params] = useSearchParams();
  const [q, setQ] = useState("");
  const [source, setSource] = useState(params.get("source") ?? "");
  const [revised, setRevised] = useState(false);
  const [fy, setFy] = useState("");
  const [currentOnly, setCurrentOnly] = useState(true);
  const emailOn = useMeta().email_enabled;
  const [priority, setPriority] = useState("");
  const [applicability, setApplicability] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<{ total: number; items: CircularBrief[] } | null>(null);
  const nav = useNavigate();

  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams({ page: String(page), size: "25" });
      if (q) p.set("q", q);
      if (source) p.set("source", source);
      if (priority) p.set("priority", priority);
      if (applicability) p.set("applicability", applicability);
      if (revised) p.set("revised", "true");
      if (fy) p.set("financial_year", fy);
      if (currentOnly && !fy) p.set("current_only", "true");
      api.get<{ total: number; items: CircularBrief[] }>(`/api/circulars?${p}`).then(setData).catch((e) => toast.error(e.message));
    }, 220);
    return () => clearTimeout(t);
  }, [q, source, priority, applicability, revised, fy, currentOnly, page]);

  const pages = data ? Math.max(1, Math.ceil(data.total / 25)) : 1;

  return (
    <div>
      <PageHeader title="Circulars" sub={data ? `${data.total} publications in the index` : "Loading…"} />
      <div className="flex flex-wrap gap-2 px-5 py-4 md:px-8">
        <div className="relative min-w-[240px] flex-1">
          <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-faint" />
          <input className="input pl-8" placeholder="Search title, reference number or text" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
        <select className="select w-auto" value={source} onChange={(e) => { setSource(e.target.value); setPage(1); }} aria-label="Type">
          <option value="">All types</option>
          <option value="notification">Notifications (circulars)</option>
          <option value="master_circular">Master circulars</option>
          <option value="master_direction">Master directions</option>
          <option value="press_release">Press releases</option>
        </select>
        <select className="select w-auto" value={priority} onChange={(e) => { setPriority(e.target.value); setPage(1); }} aria-label="Priority">
          <option value="">Any priority</option>
          <option>High</option><option>Medium</option><option>Low</option>
        </select>
        <select className="select w-auto" value={applicability} onChange={(e) => { setApplicability(e.target.value); setPage(1); }} aria-label="Applicability">
          <option value="">Any applicability</option>
          <option>Applicable</option><option>Review</option><option>For comments</option><option>Informational</option><option>Not applicable</option>
        </select>
        <label className="inline-flex items-center gap-1.5 px-1 text-[13.5px]">
          <input type="checkbox" checked={revised} onChange={(e) => { setRevised(e.target.checked); setPage(1); }} /> Revised by RBI only
        </label>
        <select className="select w-auto" value={fy} onChange={(e) => { setFy(e.target.value); setPage(1); }} aria-label="Financial year">
          <option value="">All financial years</option>
          {FY_OPTIONS.map((y) => <option key={y}>{y}</option>)}
        </select>
        <label className="inline-flex items-center gap-1.5 px-1 text-[13.5px]" title="Master circulars are reissued every year; older yearly versions are hidden unless you pick a year or untick this">
          <input type="checkbox" checked={currentOnly && !fy} disabled={!!fy} onChange={(e) => { setCurrentOnly(e.target.checked); setPage(1); }} /> Latest versions only
        </label>
      </div>
      <div className="mx-5 overflow-x-auto rounded-lg border border-line bg-surface md:mx-8">
        {!data ? (
          <div className="grid h-40 place-items-center text-muted"><Spinner /></div>
        ) : data.items.length === 0 ? (
          <Empty title="No publications match">Clear a filter, or run a check from the overview page.</Empty>
        ) : (
          <table className="data min-w-[760px]">
            <thead>
              <tr><th className="w-[104px]">Issued</th><th>Publication</th><th className="w-[100px]">Priority</th><th className="w-[130px]">For the bank</th>{emailOn && <th className="w-[110px]">Alert</th>}</tr>
            </thead>
            <tbody>
              {data.items.map((c) => (
                <tr key={c.id} className="clickable" onClick={() => nav(`/circulars/${c.id}`)}>
                  <td className="tabular-nums text-muted">{fmtDate(c.published_at)}</td>
                  <td>
                    <div className="font-serif text-[15px] leading-snug">{c.title}</div>
                    <div className="mt-0.5 flex flex-wrap items-center gap-x-2 text-[12px] text-faint">
                      <span className="font-medium text-muted">{sourceLabel(c.source)}</span>
                      {c.revision > 0 && <Tag tone="warn">Updated by RBI</Tag>}
                      {c.superseded_by && <Tag>Older version</Tag>}
                      {c.ai_summary && <Tag tone="ok">AI summary</Tag>}
                      {c.financial_year && <span>FY {c.financial_year}</span>}
                      {c.rbi_ref && <span>{c.rbi_ref}</span>}
                      {(c.listing_group || c.department) && <span>{c.listing_group || c.department}</span>}
                    </div>
                  </td>
                  <td><PriorityTag value={c.priority} /></td>
                  <td><Applicability value={c.applicability} /></td>
                  {emailOn && <td className="text-[12.5px] text-muted">{c.notified_at ? relTime(c.notified_at) : c.status === "summarized" ? "Not sent" : "–"}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      {pages > 1 && (
        <div className="flex items-center justify-end gap-2 px-5 py-4 text-[13px] md:px-8">
          <button className="btn btn-sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>Previous</button>
          <span className="text-muted">Page {page} of {pages}</span>
          <button className="btn btn-sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>Next</button>
        </div>
      )}
    </div>
  );
}

export function CircularView() {
  const { id } = useParams();
  const { user } = useAuth();
  const [c, setC] = useState<CircularDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [showText, setShowText] = useState(false);
  const nav = useNavigate();

  const load = () => api.get<CircularDetail>(`/api/circulars/${id}`).then(setC).catch((e) => toast.error(e.message));
  useEffect(() => { load(); }, [id]);
  const meta = useMeta();
  const autoTried = useRef<string | null>(null);
  // Every circular gets its own AI summary: written the first time someone opens it (if the queue has not yet).
  useEffect(() => {
    if (!c || c.ai_summary || autoTried.current === id) return;
    autoTried.current = id ?? null;
    setBusy("auto");
    api.post(`/api/circulars/${c.id}/summarize`).then(() => load()).catch(() => {}).finally(() => setBusy(null));
  }, [c?.id, c?.ai_summary]);

  if (!c) return <div className="grid h-64 place-items-center text-muted"><Spinner /></div>;
  const s = c.summary || {};

  const emailMe = async () => {
    setBusy("email");
    try {
      const r = await api.post<{ status: string; error?: string }>(`/api/circulars/${c.id}/email`);
      r.status === "failed" ? toast.error(`E-mail failed: ${r.error}`) : toast.success(r.status === "dry_run" ? "Saved to outbox (SMTP password not set)" : `Sent to ${user?.email}`);
      load();
    } catch (e: any) { toast.error(e.message); } finally { setBusy(null); }
  };
  const resummarize = async () => {
    setBusy("sum");
    try { await api.post(`/api/circulars/${c.id}/summarize`); toast.success("Summary regenerated"); load(); }
    catch (e: any) { toast.error(e.message); } finally { setBusy(null); }
  };

  return (
    <div className="pb-12">
      <div className="px-5 pt-5 md:px-8">
        <Link to="/circulars" className="inline-flex items-center gap-1 text-[13px] text-link hover:underline"><ArrowLeft size={14} /> Circulars</Link>
      </div>
      <div className="grid gap-8 px-5 pt-3 md:px-8 xl:grid-cols-[minmax(0,1fr)_320px]">
        <article className="min-w-0 max-w-[780px]">
          <div className="flex flex-wrap items-center gap-2">
            <PriorityTag value={c.priority} />
            <Applicability value={c.applicability} />
            <span className="text-[12.5px] text-faint">{sourceLabel(c.source)}</span>
            {c.revision > 0 && <Tag tone="warn">Updated by RBI {c.updated_at ? relTime(c.updated_at) : ""}</Tag>}
          </div>
          <h1 className="mt-2 text-[1.9rem] leading-[1.18]">{c.title}</h1>
          <div className="mt-2 text-[13px] text-muted">
            {[c.rbi_ref, c.dept_ref, fmtDate(c.published_at)].filter(Boolean).join("  ·  ")}
          </div>

          {c.superseded_by && (
            <div className="mt-5 rounded-md border border-gold/40 bg-gold-soft px-4 py-2.5 text-[13.5px] text-gold-text">
              This is an older yearly version (FY {c.financial_year}).{" "}
              <Link className="font-medium underline underline-offset-2" to={`/circulars/${c.superseded_by}`}>Open the latest version</Link>
            </div>
          )}
          {busy === "auto" && (
            <div className="mt-6 flex items-center gap-2 text-[13.5px] text-muted"><Spinner /> Writing the AI summary of this circular. This takes 10–40 seconds the first time.</div>
          )}
          {s.summary && <p className="mt-6 font-serif text-[1.13rem] leading-relaxed text-text">{s.summary}</p>}

          {s.action_items && s.action_items.length > 0 && (
            <section className="mt-6 border-l-[3px] border-gold bg-gold-soft px-4 py-3">
              <h2 className="text-[1.05rem]">Action for the bank</h2>
              <ul className="mt-1.5 list-disc space-y-1 pl-5 text-[14px]">{s.action_items.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </section>
          )}

          {s.key_points && s.key_points.length > 0 && (
            <section className="mt-6">
              <h2 className="text-[1.15rem]">Key points</h2>
              <ol className="mt-2 list-decimal space-y-1.5 pl-5 text-[14.5px] leading-relaxed">{s.key_points.map((k, i) => <li key={i}>{k}</li>)}</ol>
            </section>
          )}

          <section className="mt-6 grid gap-4 rounded-lg border border-line bg-surface p-4 sm:grid-cols-2">
            <div>
              <div className="label">Applicability</div>
              <div className="mt-0.5"><Applicability value={s.applicability?.verdict || c.applicability} /></div>
              <p className="text-[13px] text-muted">{s.applicability?.reason}</p>
            </div>
            <div>
              <div className="label">Priority</div>
              <div className="mt-0.5"><PriorityTag value={s.priority || c.priority} /></div>
              <p className="text-[13px] text-muted">{s.priority_reason}</p>
            </div>
            {(s.effective_date || s.deadline) && (
              <div>
                <div className="label">Effective / deadline</div>
                <p className="text-[13.5px]">{[s.effective_date, s.deadline].filter(Boolean).join(" · ")}</p>
              </div>
            )}
            {s.impacted_functions && s.impacted_functions.length > 0 && (
              <div>
                <div className="label">Functions affected</div>
                <div className="mt-1 flex flex-wrap gap-1">{s.impacted_functions.map((f) => <Tag key={f}>{f}</Tag>)}</div>
              </div>
            )}
            {s.model_view && (
              <div className="sm:col-span-2 rounded-md border border-gold/40 bg-gold-soft px-3 py-2 text-[12.5px] text-gold-text">
                The AI model read this as “{s.model_view.applicability?.verdict}”, but the title or addressee list names the entity type explicitly, so the rule's verdict is kept.
              </div>
            )}
            {s.rules_view && !s.model_view && (
              <div className="sm:col-span-2 text-[12px] text-faint">
                Rules engine view before the model: {s.rules_view.priority} priority, {s.rules_view.applicability?.verdict}. Disagreements are worth a human look.
              </div>
            )}
          </section>
          <p className="mt-2 text-[12px] text-faint">Summary by {c.summary_model || "rules"}. Read the original before acting.</p>

          <section className="mt-8">
            <button className="btn btn-sm" onClick={() => setShowText(!showText)}><FileText size={14} /> {showText ? "Hide" : "Show"} full text as indexed</button>
            {showText && <pre className="mt-3 whitespace-pre-wrap rounded-lg border border-line bg-surface p-5 font-serif text-[14.5px] leading-relaxed">{c.text}</pre>}
          </section>
        </article>

        <aside className="space-y-5 xl:pt-1">
          <div className="flex flex-col gap-2">
            <button className="btn btn-primary justify-center" onClick={() => nav(`/assistant?circular=${c.id}`)}>
              <MessageSquareText size={15} /> Chat with this circular
            </button>
            {meta.email_enabled && (
              <button className="btn justify-center" onClick={emailMe} disabled={busy === "email"}>
                {busy === "email" ? <Spinner /> : <Mail size={15} />} E-mail me this summary
              </button>
            )}
            <button className="btn justify-center" onClick={resummarize} disabled={busy === "sum" || busy === "auto"}>
              {busy === "sum" ? <Spinner /> : <RotateCcw size={15} />} {c.summary_model?.startsWith("llm") ? "Regenerate AI summary" : "Generate AI summary"}
            </button>
          </div>
          <dl className="space-y-3 rounded-lg border border-line bg-surface p-4 text-[13px]">
            <Meta k="Original"><a className="inline-flex items-center gap-1 text-link hover:underline" href={c.url} target="_blank" rel="noreferrer">rbi.org.in <ExternalLink size={12} /></a>{c.pdf_url && <> · <a className="text-link hover:underline" href={c.pdf_url} target="_blank" rel="noreferrer">PDF</a></>}</Meta>
            {c.listing_group && <Meta k="RBI listing">{c.listing_group}</Meta>}
            {c.financial_year && <Meta k="Financial year">{c.financial_year}</Meta>}
            {c.department && c.department !== c.listing_group && <Meta k="Department">{c.department}</Meta>}
            {c.addressees && <Meta k="Addressed to">{c.addressees}</Meta>}
            {c.signatory && <Meta k="Signed by">{c.signatory}</Meta>}
            <Meta k="Indexed">{fmtDate(c.created_at, true)} · {c.chunk_count} passages</Meta>
            {c.tags?.length > 0 && <Meta k="Topics"><div className="flex flex-wrap gap-1">{c.tags.map((t) => <Tag key={t}>{t}</Tag>)}</div></Meta>}
            {c.ingest_trace_id && <Meta k="Provenance"><Link className="text-link hover:underline" to={`/traces?id=${c.ingest_trace_id}`}>Ingestion trace</Link></Meta>}
          </dl>
          {meta.email_enabled && <div className="rounded-lg border border-line bg-surface p-4">
            <div className="label mb-2">E-mails about this publication</div>
            {c.emails.length === 0 ? <p className="text-[13px] text-faint">None sent.</p> : (
              <ul className="space-y-2 text-[12.5px]">
                {c.emails.map((e, i) => (
                  <li key={i} className="flex items-start justify-between gap-2">
                    <span className="text-muted">{e.kind} to {e.recipients.join(", ")}<br /><span className="text-faint">{fmtDate(e.ts, true)}</span></span>
                    <StatusTag status={e.status} />
                  </li>
                ))}
              </ul>
            )}
          </div>}
        </aside>
      </div>
    </div>
  );
}

function Meta({ k, children }: { k: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[12px] text-muted">{k}</dt>
      <dd className="mt-0.5 text-text">{children}</dd>
    </div>
  );
}

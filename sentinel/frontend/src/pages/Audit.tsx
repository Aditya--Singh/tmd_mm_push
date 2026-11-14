import { Download, ShieldAlert, ShieldCheck } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { PageHeader, Spinner } from "../components/ui";
import { api } from "../lib/api";
import { fmtDate } from "../lib/format";

type Ev = { id: number; ts: string; actor: string; action: string; resource: string; details: any; ip: string | null; trace_id: string | null; hash: string; prev_hash: string };
type Verify = { intact: boolean; verified: number; head?: string; broken_at_id?: number; reason?: string };

export default function Audit() {
  const [action, setAction] = useState("");
  const [actor, setActor] = useState("");
  const [data, setData] = useState<{ total: number; actions: string[]; items: Ev[] } | null>(null);
  const [verify, setVerify] = useState<Verify | null>(null);
  const [checking, setChecking] = useState(false);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams({ limit: "200" });
      if (action) p.set("action", action);
      if (actor) p.set("actor", actor);
      api.get<typeof data>(`/api/audit?${p}`).then(setData).catch((e) => toast.error(e.message));
    }, 200);
    return () => clearTimeout(t);
  }, [action, actor]);

  const runVerify = async () => {
    setChecking(true);
    try { setVerify(await api.get<Verify>("/api/audit/verify")); } finally { setChecking(false); }
  };
  useEffect(() => { runVerify(); }, []);

  return (
    <div className="pb-10">
      <PageHeader
        title="Audit trail"
        sub="Who did what, when — sign-ins, questions, e-mails, setting changes and agent runs. Each record is chained to the previous one by its SHA-256 hash, so any edit to history is detectable."
        actions={<button className="btn" onClick={() => api.download("/api/audit/export.csv", "audit-trail.csv").catch((e) => toast.error(e.message))}><Download size={14} /> Export CSV</button>}
      />
      <div className="mx-5 mt-4 md:mx-8">
        {!verify || checking ? (
          <div className="flex items-center gap-2 rounded-lg border border-line bg-surface px-4 py-3 text-[13.5px] text-muted"><Spinner /> Verifying the hash chain…</div>
        ) : verify.intact ? (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-ok/30 bg-ok-soft px-4 py-3 text-[13.5px] text-ok">
            <ShieldCheck size={18} />
            <span><b className="font-medium">Chain intact.</b> All {verify.verified} records verified from the first entry.</span>
            <span className="font-mono text-[12px] opacity-80">head {verify.head?.slice(0, 16)}…</span>
            <button className="btn btn-sm ml-auto" onClick={runVerify}>Verify again</button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-maroon/30 bg-maroon-soft px-4 py-3 text-[13.5px] text-maroon">
            <ShieldAlert size={18} />
            <span><b className="font-medium">Chain broken at record #{verify.broken_at_id}</b> ({verify.reason}). {verify.verified} earlier records verified. Treat later records as untrusted and investigate.</span>
            <button className="btn btn-sm ml-auto" onClick={runVerify}>Verify again</button>
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-2 px-5 py-3 md:px-8">
        <select className="select w-auto" value={action} onChange={(e) => setAction(e.target.value)} aria-label="Action">
          <option value="">All actions</option>{data?.actions.map((a) => <option key={a}>{a}</option>)}
        </select>
        <input className="input max-w-xs" placeholder="Filter by user" value={actor} onChange={(e) => setActor(e.target.value)} />
      </div>
      <div className="mx-5 overflow-x-auto rounded-lg border border-line bg-surface md:mx-8">
        {!data ? <div className="p-6"><Spinner /></div> : (
          <table className="data min-w-[880px]">
            <thead><tr><th className="w-[60px]">#</th><th className="w-[160px]">Time (IST)</th><th>User</th><th>Action</th><th>Resource</th><th className="w-[120px]">Hash</th><th className="w-[80px]">Trace</th></tr></thead>
            <tbody>
              {data.items.map((e) => (
                <Fragment key={e.id}>
                  <tr className="clickable" onClick={() => setOpen(open === e.id ? null : e.id)}>
                    <td className="tabular-nums text-faint">{e.id}</td>
                    <td className="tabular-nums text-muted">{fmtDate(e.ts, true)}</td>
                    <td>{e.actor}{e.ip && <div className="text-[11.5px] text-faint">{e.ip}</div>}</td>
                    <td className={e.action.includes("failed") || e.action.includes("blocked") ? "text-maroon" : ""}>{e.action}</td>
                    <td className="max-w-[260px] truncate text-muted">{e.resource}</td>
                    <td className="font-mono text-[11.5px] text-faint" title={e.hash}>{e.hash.slice(0, 12)}</td>
                    <td>{e.trace_id ? <Link className="text-link hover:underline" onClick={(x) => x.stopPropagation()} to={`/traces?id=${e.trace_id}`}>open</Link> : "–"}</td>
                  </tr>
                  {open === e.id && (
                    <tr>
                      <td colSpan={7} className="bg-surface-2">
                        <pre className="json text-muted">{JSON.stringify({ details: e.details, prev_hash: e.prev_hash, hash: e.hash }, null, 2)}</pre>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

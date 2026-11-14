import { useEffect, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { Empty, PageHeader, Spinner, StatusTag } from "../components/ui";
import { api } from "../lib/api";
import { fmtDate } from "../lib/format";
import { useLiveListener } from "../lib/live";

type Email = { id: number; ts: string; kind: string; recipients: string[]; subject: string; status: string; error: string | null; circular_ids: number[] | null; trace_id: string | null; triggered_by: string | null };
const KIND: Record<string, string> = { alert: "New-publication alert", digest: "Digest", summary: "Circular summary", answer: "Assistant answer", test: "Test" };

export default function Alerts() {
  const [rows, setRows] = useState<Email[] | null>(null);
  const load = () => api.get<Email[]>("/api/emails").then(setRows).catch((e) => toast.error(e.message));
  useEffect(() => { load(); }, []);
  useLiveListener((ev) => { if (ev.type === "audit" && ev.action === "email.send") load(); }, []);

  return (
    <div className="pb-10">
      <PageHeader title="Alert e-mails" sub="Everything Sentinel has sent or tried to send, with the agent trace behind each message." />
      <div className="mx-5 mt-5 overflow-x-auto rounded-lg border border-line bg-surface md:mx-8">
        {!rows ? <div className="p-6"><Spinner /></div> : rows.length === 0 ? (
          <Empty title="No e-mails yet">Alerts go out when the RBI publishes something new after the first (baseline) check. You can also send a test from Settings.</Empty>
        ) : (
          <table className="data min-w-[860px]">
            <thead><tr><th className="w-[150px]">Time (IST)</th><th className="w-[150px]">Type</th><th>Subject</th><th>To</th><th className="w-[90px]">Status</th><th className="w-[70px]">Trace</th></tr></thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id}>
                  <td className="tabular-nums text-muted">{fmtDate(e.ts, true)}</td>
                  <td>{KIND[e.kind] ?? e.kind}<div className="text-[11.5px] text-faint">by {e.triggered_by}</div></td>
                  <td>
                    {e.subject}
                    {e.circular_ids && e.circular_ids.length > 0 && (
                      <div className="mt-0.5 text-[12px]">{e.circular_ids.slice(0, 6).map((id) => <Link key={id} className="mr-2 text-link hover:underline" to={`/circulars/${id}`}>#{id}</Link>)}</div>
                    )}
                    {e.error && <div className="mt-0.5 text-[12px] text-maroon">{e.error}</div>}
                  </td>
                  <td className="text-[12.5px] text-muted">{e.recipients.join(", ")}</td>
                  <td><StatusTag status={e.status} /></td>
                  <td>{e.trace_id ? <Link className="text-link hover:underline" to={`/traces?id=${e.trace_id}`}>open</Link> : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <p className="mx-5 mt-3 text-[12px] text-faint md:mx-8">“Dry run” means no SMTP password is configured; the message was written to the server's data/outbox folder instead of being sent.</p>
    </div>
  );
}

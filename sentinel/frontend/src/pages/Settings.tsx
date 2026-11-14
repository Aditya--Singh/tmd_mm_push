import { Plus, Send, X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Field, PageHeader, Spinner, StatusTag, Tag } from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useMeta } from "../lib/meta";
import { relTime } from "../lib/format";
import type { User } from "../lib/types";

type Runtime = { subscribers: string[]; sync_interval_minutes: number; notifications_enabled: boolean; digest_threshold: number; notify_priorities: string[]; baseline_done: boolean };
type System = {
  feeds: { source: string; url: string }[];
  llm: { provider: string; model: string; base_url: string | null; healthy: boolean | null; last_error: string | null };
  embedding_model: string; embedding_fallback: string | null; reranker: string | null; index_chunks: number;
  smtp: { host: string; port: number; username: string; from: string; password_configured: boolean };
  notify_on_first_sync: boolean; public_url: string;
};

export default function Settings() {
  const { user, refresh } = useAuth();
  const meta = useMeta();
  const admin = user?.role === "admin";
  const [rt, setRt] = useState<Runtime | null>(null);
  const [sys, setSys] = useState<System | null>(null);
  const [newEmail, setNewEmail] = useState("");
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () => api.get<{ runtime: Runtime; system: System }>("/api/settings").then((r) => { setRt(r.runtime); setSys(r.system); });
  useEffect(() => { load().catch((e) => toast.error(e.message)); }, []);
  useEffect(() => { if (location.hash === "#password") setTimeout(() => document.getElementById("password")?.scrollIntoView(), 100); }, []);

  const save = async () => {
    if (!rt) return;
    setSaving(true);
    try {
      const r = await api.put<Runtime>("/api/settings", {
        subscribers: rt.subscribers, sync_interval_minutes: rt.sync_interval_minutes, notifications_enabled: rt.notifications_enabled,
        digest_threshold: rt.digest_threshold, notify_priorities: rt.notify_priorities,
      });
      setRt(r);
      toast.success("Settings saved");
    } catch (e: any) { toast.error(e.message); } finally { setSaving(false); }
  };

  const action = async (key: string, fn: () => Promise<any>) => {
    setBusy(key);
    try { await fn(); } catch (e: any) { toast.error(e.message); } finally { setBusy(null); }
  };

  const addEmail = () => {
    const e = newEmail.trim().toLowerCase();
    if (!rt || !e) return;
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e)) { toast.error("That is not a valid e-mail address."); return; }
    if (!rt.subscribers.includes(e)) setRt({ ...rt, subscribers: [...rt.subscribers, e] });
    setNewEmail("");
  };

  if (!rt || !sys) return <div className="grid h-64 place-items-center text-muted"><Spinner /></div>;

  return (
    <div className="pb-14">
      <PageHeader title="Settings" sub="Schedule and system configuration. Every change is written to the audit trail."
        actions={admin && <button className="btn btn-primary" onClick={save} disabled={saving}>{saving && <Spinner />} Save changes</button>} />
      <div className="mx-auto grid max-w-[1100px] gap-6 px-5 py-6 md:px-8 lg:grid-cols-2">
        <section className="panel p-5">
          <h2 className="text-[1.2rem]">Schedule</h2>
          <div className="mt-3 max-w-xs">
            <Field label="Check the RBI website every" hint="Minutes between automatic checks (5–1440).">
              <input className="input" type="number" min={5} max={1440} disabled={!admin} value={rt.sync_interval_minutes} onChange={(e) => setRt({ ...rt, sync_interval_minutes: Number(e.target.value) })} />
            </Field>
          </div>
          <p className="mt-3 text-[12.5px] text-faint">While a first-time backlog remains (for example all years of Master Circulars), the next check starts straight away.</p>
        </section>

        {meta.email_enabled && (
        <section className="panel p-5">
          <h2 className="text-[1.2rem]">Alert recipients</h2>
          <p className="mt-1 text-[13px] text-muted">New RBI publications are e-mailed to these addresses from {sys.smtp.from}.</p>
          <ul className="mt-3 flex flex-wrap gap-1.5">
            {rt.subscribers.map((e) => (
              <li key={e} className="inline-flex items-center gap-1 rounded-md border border-line bg-surface-2 py-1 pl-2.5 pr-1 text-[13px]">
                {e}
                {admin && <button className="rounded p-0.5 text-faint hover:text-maroon" onClick={() => setRt({ ...rt, subscribers: rt.subscribers.filter((x) => x !== e) })} aria-label={`Remove ${e}`}><X size={13} /></button>}
              </li>
            ))}
            {rt.subscribers.length === 0 && <li className="text-[13px] text-maroon">No recipients — alerts will not be delivered.</li>}
          </ul>
          {admin && (
            <div className="mt-3 flex gap-2">
              <input className="input" placeholder="name@pnb.bank.in" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addEmail()} />
              <button className="btn" onClick={addEmail}><Plus size={14} /> Add</button>
            </div>
          )}
          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <Field label="Send one digest when a check finds" hint="This many or more new items; fewer are sent individually.">
              <input className="input" type="number" min={2} max={50} disabled={!admin} value={rt.digest_threshold} onChange={(e) => setRt({ ...rt, digest_threshold: Number(e.target.value) })} />
            </Field>
          </div>
          <fieldset className="mt-4">
            <legend className="label">Alert on these priorities</legend>
            <div className="mt-1.5 flex gap-4 text-[13.5px]">
              {["High", "Medium", "Low"].map((p) => (
                <label key={p} className="inline-flex items-center gap-1.5">
                  <input type="checkbox" disabled={!admin} checked={rt.notify_priorities.includes(p)}
                    onChange={(e) => setRt({ ...rt, notify_priorities: e.target.checked ? [...rt.notify_priorities, p] : rt.notify_priorities.filter((x) => x !== p) })} />
                  {p}
                </label>
              ))}
            </div>
          </fieldset>
          <label className="mt-4 flex items-center gap-2 text-[13.5px]">
            <input type="checkbox" disabled={!admin} checked={rt.notifications_enabled} onChange={(e) => setRt({ ...rt, notifications_enabled: e.target.checked })} />
            Send alert e-mails automatically
          </label>
          {admin && (
            <button className="btn mt-5" disabled={busy === "test"} onClick={() => action("test", async () => {
              const r = await api.post<{ status: string; error?: string }>("/api/settings/test-email");
              r.status === "failed" ? toast.error(`Test failed: ${r.error}`) : toast.success(r.status === "dry_run" ? "Test written to the outbox (no SMTP password)" : `Test sent (${r.status})`);
            })}>{busy === "test" ? <Spinner /> : <Send size={14} />} Send a test e-mail to recipients</button>
          )}
          {!sys.smtp.password_configured && (
            <p className="mt-3 rounded-md border border-gold/40 bg-gold-soft px-3 py-2 text-[12.5px] text-gold-text">
              No SMTP password is set, so e-mails are saved to the server's outbox folder instead of being sent. Set <code className="font-mono">SMTP_PASSWORD</code> to a Gmail app password for {sys.smtp.username} and restart.
            </p>
          )}
        </section>
        )}

        <section className="panel p-5">
          <h2 className="text-[1.2rem]">System</h2>
          <dl className="mt-3 space-y-3 text-[13.5px]">
            <Row k="Language model">
              {sys.llm.provider === "none" ? "Not configured — agents use rules and extractive summaries" : <>{sys.llm.model} <span className="text-muted">via {sys.llm.provider}{sys.llm.base_url ? ` at ${sys.llm.base_url}` : ""}</span></>}
              <div className="mt-1 flex items-center gap-2">
                {sys.llm.healthy === true && <StatusTag status="healthy" />}
                {sys.llm.healthy === false && <StatusTag status="degraded" />}
                {admin && sys.llm.provider !== "none" && (
                  <button className="btn btn-sm" disabled={busy === "llm"} onClick={() => action("llm", async () => {
                    const r = await api.post<System["llm"]>("/api/system/llm-check");
                    r.healthy ? toast.success("Model responded") : toast.error(`Model check failed: ${r.last_error}`);
                    load();
                  })}>{busy === "llm" && <Spinner />} Check model</button>
                )}
              </div>
              {sys.llm.last_error && <div className="mt-1 text-[12px] text-maroon">{sys.llm.last_error}</div>}
            </Row>
            <Row k="Embeddings">{sys.embedding_model}{sys.embedding_fallback && <div className="mt-1 text-[12px] text-gold-text">{sys.embedding_fallback}</div>}</Row>
            <Row k="Reranker">{sys.reranker || "Off"}</Row>
            <Row k="Search index">
              {sys.index_chunks} passages
              {admin && <button className="btn btn-sm ml-2" disabled={busy === "reindex"} onClick={() => action("reindex", async () => { const r = await api.post<{ chunks: number }>("/api/system/reindex"); toast.success(`Index rebuilt: ${r.chunks} passages`); load(); })}>{busy === "reindex" && <Spinner />} Rebuild</button>}
            </Row>
            <Row k="RBI sources">{sys.feeds.map((f) => <div key={f.url} className="break-all text-[12.5px]"><span className="text-muted">{f.source}:</span> {f.url}</div>)}</Row>
            {meta.email_enabled && <Row k="Mail server">{sys.smtp.host}:{sys.smtp.port} as {sys.smtp.username} <Tag tone={sys.smtp.password_configured ? "ok" : "warn"}>{sys.smtp.password_configured ? "password set" : "dry run"}</Tag></Row>}
            <Row k="First check">{rt.baseline_done ? "Baseline built — new items are alerted" : sys.notify_on_first_sync ? "Will alert everything found" : "Will index silently, then alert new items"}</Row>
          </dl>
          <p className="mt-4 text-[12px] text-faint">Model, embedding and SMTP settings come from the server's .env file and need a restart to change.</p>
        </section>

        {admin && meta.auth_enabled && <Users />}
        {meta.auth_enabled && <PasswordForm onDone={refresh} />}
      </div>
    </div>
  );
}

function Row({ k, children }: { k: string; children: React.ReactNode }) {
  return <div className="grid grid-cols-[120px_1fr] gap-3"><dt className="text-muted">{k}</dt><dd className="min-w-0">{children}</dd></div>;
}

function Users() {
  const [users, setUsers] = useState<User[] | null>(null);
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "analyst" });
  const [busy, setBusy] = useState(false);
  const load = () => api.get<User[]>("/api/users").then(setUsers);
  useEffect(() => { load(); }, []);
  const create = async () => {
    setBusy(true);
    try { await api.post("/api/users", form); toast.success(`${form.email} added. They must change the password at first sign-in.`); setForm({ name: "", email: "", password: "", role: "analyst" }); load(); }
    catch (e: any) { toast.error(e.message); } finally { setBusy(false); }
  };
  const patch = async (id: number, body: Partial<User>) => {
    try { await api.patch(`/api/users/${id}`, body); load(); } catch (e: any) { toast.error(e.message); }
  };
  return (
    <section className="panel p-5 lg:col-span-2">
      <h2 className="text-[1.2rem]">People</h2>
      <div className="mt-3 overflow-x-auto">
        <table className="data min-w-[640px]">
          <thead><tr><th>Name</th><th>E-mail</th><th>Role</th><th>Last sign-in</th><th>Status</th></tr></thead>
          <tbody>
            {users?.map((u) => (
              <tr key={u.id}>
                <td>{u.name}</td>
                <td className="text-muted">{u.email}</td>
                <td>
                  <select className="select h-8 w-auto" value={u.role} onChange={(e) => patch(u.id, { role: e.target.value as User["role"] })} aria-label={`Role for ${u.email}`}>
                    <option value="analyst">Analyst</option><option value="admin">Administrator</option>
                  </select>
                </td>
                <td className="text-muted">{relTime(u.last_login_at)}</td>
                <td><button className="btn btn-sm" onClick={() => patch(u.id, { is_active: !u.is_active })}>{u.is_active ? "Deactivate" : "Reactivate"}</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-[1fr_1fr_1fr_auto_auto]">
        <input className="input" placeholder="Full name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        <input className="input" placeholder="name@pnb.bank.in" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
        <input className="input" type="password" placeholder="Temporary password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
        <select className="select w-auto" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} aria-label="Role"><option value="analyst">Analyst</option><option value="admin">Administrator</option></select>
        <button className="btn" disabled={busy || !form.email || !form.name || !form.password} onClick={create}>{busy ? <Spinner /> : <Plus size={14} />} Add person</button>
      </div>
      <p className="mt-2 text-[12px] text-faint">Passwords need 10+ characters with upper and lower case, a digit and a symbol.</p>
    </section>
  );
}

function PasswordForm({ onDone }: { onDone: () => void }) {
  const [cur, setCur] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    setBusy(true);
    try { await api.post("/api/auth/change-password", { current_password: cur, new_password: next }); toast.success("Password changed"); setCur(""); setNext(""); onDone(); }
    catch (e: any) { toast.error(e.message); } finally { setBusy(false); }
  };
  return (
    <section id="password" className="panel p-5">
      <h2 className="text-[1.2rem]">Your password</h2>
      <div className="mt-3 space-y-3">
        <Field label="Current password"><input className="input" type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} /></Field>
        <Field label="New password" hint="10+ characters with upper and lower case, a digit and a symbol."><input className="input" type="password" autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} /></Field>
        <button className="btn btn-primary" disabled={busy || !cur || !next} onClick={submit}>{busy && <Spinner />} Change password</button>
      </div>
    </section>
  );
}

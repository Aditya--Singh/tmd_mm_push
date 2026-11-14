import { Eye, EyeOff } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Navigate } from "react-router";
import { Seal, Spinner } from "../components/ui";
import { useAuth } from "../lib/auth";
import { useMeta } from "../lib/meta";

// The four kinds of RBI publication Sentinel files, as they appear on the RBI website.
const REGISTER = [
  ["Master Direction", "Oct 07, 2026", "Credit Valuation Adjustment Framework"],
  ["Master Circular", "Oct 01, 2026", "Credit Facilities to SCs & STs"],
  ["Notification", "Oct 27, 2026", "UAPA sanctions list amendment"],
  ["Notification", "Oct 23, 2026", "Leverage ratio framework"],
  ["Press release", "Oct 27, 2026", "Monetary penalty on a co-operative bank"],
];

export default function Login() {
  const { user, login } = useAuth();
  const meta = useMeta();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (user || !meta.auth_enabled) return <Navigate to="/" replace />;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden overflow-hidden border-t-[4px] border-gold bg-ink px-14 py-12 text-white lg:flex lg:flex-col">
        <div className="flex items-center gap-3">
          <Seal size={36} />
          <div className="leading-tight">
            <div className="font-serif text-xl">Regulatory Sentinel</div>
            <div className="text-[12.5px] text-[#d9aab6]">{meta.org_name}, {meta.org_unit}</div>
          </div>
        </div>
        <div className="mt-auto max-w-xl">
          <h1 className="font-serif text-[2.6rem] leading-[1.12] text-white">
            Every RBI circular, Master Circular and Master Direction read, filed and explained.
          </h1>
          <p className="mt-5 max-w-md text-[15px] leading-relaxed text-[#e3c3cb]">
            Agents watch the Reserve Bank's website, index each new or revised document, tell you whether it applies to
            {" "}{meta.org_short}, e-mail an alert, and answer questions with the paragraph they came from.
          </p>
        </div>
        <div className="mt-12 border-t border-white/15 pt-5">
          <div className="mb-3 text-[12px] text-[#d9aab6]">Recently filed</div>
          <table className="w-full text-[12.5px]">
            <tbody>
              {REGISTER.map(([a, b, c], i) => (
                <tr key={a} className="border-b border-white/[0.06]" style={{ opacity: 1 - i * 0.14 }}>
                  <td className="py-1.5 pr-4 font-medium text-gold">{a}</td>
                  <td className="hidden py-1.5 pr-4 tabular-nums text-[#d9aab6] xl:table-cell">{b}</td>
                  <td className="py-1.5 text-[#f2dfe4]">{c}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="flex items-center justify-center bg-surface px-6 py-12">
        <form onSubmit={submit} className="w-full max-w-[360px]" noValidate>
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <Seal size={30} onDark={false} />
            <span className="font-serif text-xl">Regulatory Sentinel</span>
          </div>
          <h2 className="text-[1.7rem]">Sign in</h2>
          <p className="mt-1 text-[13.5px] text-muted">Use your {meta.org_short} e-mail address and Sentinel password.</p>

          <label className="mt-7 block">
            <span className="label">E-mail address</span>
            <input className="input mt-1" type="email" autoComplete="username" required autoFocus value={email}
              onChange={(e) => setEmail(e.target.value)} placeholder="name@pnb.bank.in" />
          </label>
          <label className="mt-4 block">
            <span className="label">Password</span>
            <div className="relative mt-1">
              <input className="input pr-10" type={show ? "text" : "password"} autoComplete="current-password" required value={password}
                onChange={(e) => setPassword(e.target.value)} />
              <button type="button" className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded p-1.5 text-muted hover:text-text"
                onClick={() => setShow(!show)} aria-label={show ? "Hide password" : "Show password"}>
                {show ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </label>

          {error && (
            <div role="alert" className="mt-4 rounded-md border border-maroon/30 bg-maroon-soft px-3 py-2 text-[13px] text-maroon">
              {error}
            </div>
          )}

          <button className="btn btn-primary mt-6 h-10 w-full justify-center" disabled={busy || !email || !password}>
            {busy ? <Spinner /> : null} Sign in
          </button>

          <p className="mt-6 text-[12px] leading-relaxed text-faint">
            Every sign-in, question and alert is recorded in a tamper-evident audit trail. The first administrator account
            and its temporary password come from the server's <code className="font-mono">.env</code> file.
          </p>
        </form>
      </section>
    </div>
  );
}

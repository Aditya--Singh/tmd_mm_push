import { useEffect, useState } from "react";

type Status = "checking" | "online" | "offline";

const STATUS_STYLE: Record<Status, { dot: string; label: string }> = {
  checking: { dot: "bg-slate-300", label: "Checking services…" },
  online: { dot: "bg-emerald-500", label: "Services online" },
  offline: { dot: "bg-red-500", label: "Backend offline" },
};

export default function Header() {
  const [status, setStatus] = useState<Status>("checking");

  useEffect(() => {
    let cancelled = false;
    fetch("/api/health")
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(() => !cancelled && setStatus("online"))
      .catch(() => !cancelled && setStatus("offline"));
    return () => {
      cancelled = true;
    };
  }, []);

  const s = STATUS_STYLE[status];

  return (
    <header className="bg-white">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-5">
        <div className="flex items-center gap-4">
          <div
            aria-hidden="true"
            className="flex h-12 w-12 flex-col items-center justify-center rounded-lg bg-pnb-maroon shadow-sm"
          >
            <span className="text-sm font-bold tracking-wide text-white">PNB</span>
            <span className="mt-0.5 h-0.5 w-7 rounded bg-pnb-gold" />
          </div>
          <div className="leading-tight">
            <p className="text-lg font-semibold text-pnb-maroon">Punjab National Bank</p>
            <p className="text-sm text-slate-500">Employee Productivity Tool</p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500" role="status">
          <span className={`h-2 w-2 rounded-full ${s.dot}`} />
          <span className="hidden sm:inline">{s.label}</span>
        </div>
      </div>
      <div className="h-1 bg-gradient-to-r from-pnb-maroon via-pnb-maroon to-pnb-gold" />
    </header>
  );
}

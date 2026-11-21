import { useEffect, useState } from "react";

type Status = "checking" | "online" | "offline";

const STATUS_STYLE: Record<Status, { dot: string; label: string }> = {
  checking: { dot: "bg-slate-300", label: "Checking services…" },
  online: { dot: "bg-emerald-500", label: "Services online" },
  offline: { dot: "bg-red-500", label: "Backend offline" },
};

/**
 * Whether the services of this machine are answering.
 *
 * The hub draws the chrome of the platform, so the tool shows nothing of its own
 * at the top: this little sign stands at the right of the tools instead.
 */
export default function ServiceStatus() {
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
    <div className="flex items-center gap-2 text-xs text-slate-500" role="status">
      <span className={`h-2 w-2 rounded-full ${s.dot}`} />
      <span>{s.label}</span>
    </div>
  );
}

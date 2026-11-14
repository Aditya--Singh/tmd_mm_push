import clsx from "clsx";
import { Check, Loader2, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useMeta } from "../lib/meta";

/**
 * Organisation mark. Put the bank's official logo at frontend/public/brand/logo.png (or .svg) and rebuild;
 * until then a plain monogram badge with the short name is shown. The official logo is not drawn here.
 */
export function Seal({ size = 28, onDark = true }: { size?: number; onDark?: boolean }) {
  const meta = useMeta();
  const [src, setSrc] = useState<string | null>("/brand/logo.png");
  if (src) {
    return (
      <img
        src={src}
        alt={meta.org_short}
        height={size}
        style={{ height: size, width: "auto", maxWidth: size * 3.2 }}
        className={onDark ? "rounded-[3px] bg-white p-[2px]" : ""}
        onError={() => setSrc(src.endsWith(".png") ? "/brand/logo.svg" : null)}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className="inline-grid flex-none place-items-center rounded-[5px] font-sans font-semibold tracking-[0.02em]"
      style={{
        width: size * 1.45,
        height: size,
        fontSize: size * 0.42,
        background: onDark ? "var(--gold)" : "#8e1b33",
        color: onDark ? "#3a0a16" : "#ffd36b",
      }}
    >
      {meta.org_short}
    </span>
  );
}

export function PageHeader({ title, sub, actions }: { title: string; sub?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3 border-b border-line px-5 pb-4 pt-6 md:px-8">
      <div className="min-w-0">
        <h1 className="text-[1.65rem] leading-tight text-text">{title}</h1>
        {sub && <div className="mt-1 text-[13.5px] text-muted">{sub}</div>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

const PRIO: Record<string, string> = {
  High: "bg-maroon-soft text-maroon border-maroon/30",
  Medium: "bg-gold-soft text-gold-text border-gold/40",
  Low: "bg-slate-soft text-slate border-slate/25",
};

export function PriorityTag({ value, className }: { value?: string | null; className?: string }) {
  if (!value) return null;
  return (
    <span className={clsx("inline-flex h-[21px] items-center rounded border px-1.5 text-[11.5px] font-medium", PRIO[value] ?? PRIO.Low, className)}>
      {value}
    </span>
  );
}

const APPLIC: Record<string, string> = {
  // keys match the backend's applicability verdicts
  Applicable: "text-ok",
  "Not applicable": "text-faint",
  Informational: "text-slate",
  "For comments": "text-gold-text",
  Review: "text-gold-text",
};

export function Applicability({ value }: { value?: string | null }) {
  if (!value) return null;
  return <span className={clsx("text-[12.5px] font-medium", APPLIC[value] ?? "text-muted")}>{value}</span>;
}

export function Tag({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "ok" | "warn" | "bad" | "info" }) {
  const tones = {
    neutral: "bg-surface-2 text-muted border-line",
    ok: "bg-ok-soft text-ok border-ok/30",
    warn: "bg-gold-soft text-gold-text border-gold/40",
    bad: "bg-maroon-soft text-maroon border-maroon/30",
    info: "bg-slate-soft text-slate border-slate/25",
  };
  return <span className={clsx("inline-flex h-[21px] items-center gap-1 rounded border px-1.5 text-[11.5px] font-medium", tones[tone])}>{children}</span>;
}

export function StatusTag({ status }: { status: string }) {
  const map: Record<string, "ok" | "bad" | "warn" | "info" | "neutral"> = {
    ok: "ok", sent: "ok", healthy: "ok", Grounded: "ok", intact: "ok",
    error: "bad", failed: "bad", degraded: "bad", "Weakly grounded": "bad",
    running: "info", dry_run: "warn", "Partially grounded": "warn", cancelled: "warn", disabled: "neutral",
    Abstained: "info", idle: "neutral",
  };
  const label = status === "dry_run" ? "dry run" : status;
  return <Tag tone={map[status] ?? "neutral"}>{label}</Tag>;
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={clsx("animate-spin", className)} size={16} aria-label="Loading" />;
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="mx-auto max-w-md px-6 py-14 text-center">
      <h3 className="text-lg text-text">{title}</h3>
      {children && <div className="mt-1.5 text-[13.5px] text-muted">{children}</div>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </div>
  );
}

export function Stamp({ status }: { status: "running" | "done" | "error" | "waiting" }) {
  if (status === "done") return <span className="stamp stamp-done"><Check size={13} strokeWidth={3} /></span>;
  if (status === "error") return <span className="stamp stamp-err"><X size={13} strokeWidth={3} /></span>;
  if (status === "running") return <span className="stamp stamp-run" />;
  return <span className="stamp stamp-wait" />;
}

export function Field({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <label className="block">
      <span className="label">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <div className="mt-1 text-[12px] text-faint">{hint}</div>}
    </label>
  );
}

export function JsonView({ value }: { value: unknown }) {
  if (value == null) return <div className="text-[12px] text-faint">None recorded</div>;
  return <pre className="json max-h-[360px] overflow-auto rounded-md border border-line bg-surface-2 p-3 text-text">{JSON.stringify(value, null, 2)}</pre>;
}

// readable on both light paper and the dark theme; maroon/gold family plus a few neutrals
export const AGENT_COLORS: Record<string, string> = {
  Watcher: "#b2453f",
  Ingestion: "#a0603a",
  Summarizer: "#c48a00",
  Indexer: "#7d6b5f",
  Notifier: "#b5294a",
  Router: "#9a3b5c",
  Retriever: "#4f7395",
  Answer: "#d39b12",
  Verifier: "#3f8a5f",
  Memory: "#7c5a9a",
  Briefing: "#b07a1c",
  Resolver: "#6b7f99",
  LLM: "#9a8a90",
  Sync: "#b2453f",
  Email: "#b5294a",
  System: "#7d6b5f",
};
export const agentColor = (a: string) => AGENT_COLORS[a] ?? "#5b6475";

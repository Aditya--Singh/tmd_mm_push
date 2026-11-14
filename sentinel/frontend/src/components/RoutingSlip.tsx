import clsx from "clsx";
import { ExternalLink } from "lucide-react";
import { Link } from "react-router";
import { fmtMs } from "../lib/format";
import type { Source, StepEvent, Verification } from "../lib/types";
import { Stamp, StatusTag, agentColor } from "./ui";

/**
 * The routing slip: like a file moving between desks in a bank, each agent that handled the
 * question "initials" it in order, with what it decided and how long it took.
 */
export function RoutingSlip({
  steps,
  verification,
  sources,
  traceId,
  activeCite,
  onCite,
  live,
}: {
  steps: StepEvent[];
  verification?: Verification | null;
  sources: Source[];
  traceId?: string | null;
  activeCite?: number | null;
  onCite?: (n: number) => void;
  live?: boolean;
}) {
  return (
    <div className="space-y-6">
      <section>
        <div className="mb-2 flex items-baseline justify-between">
          <h3 className="text-[1.05rem]">Routing slip</h3>
          {traceId && (
            <Link to={`/traces?id=${traceId}`} className="inline-flex items-center gap-1 text-[12px] text-link hover:underline">
              Full trace <ExternalLink size={12} />
            </Link>
          )}
        </div>
        {steps.length === 0 ? (
          <p className="text-[13px] text-muted">{live ? "Waiting for the first agent…" : "Select an answer to see which agents handled it."}</p>
        ) : (
          <ol className="relative">
            {steps.map((s, i) => (
              <li key={`${s.agent}-${s.label}-${i}`} className="relative flex gap-3 pb-3.5">
                {i < steps.length - 1 && <span className="absolute left-[10.5px] top-[24px] bottom-0 w-px bg-line-strong" />}
                <Stamp status={s.status} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[13.5px] font-medium" style={{ color: agentColor(s.agent) }}>{s.agent}</span>
                    <span className="text-[11.5px] tabular-nums text-faint">{s.status === "running" ? "working" : fmtMs(s.ms)}</span>
                  </div>
                  <div className="text-[12.5px] text-muted">{s.label}</div>
                  {s.detail && s.status !== "running" && <StepDetail detail={s.detail} />}
                </div>
              </li>
            ))}
          </ol>
        )}
      </section>

      {verification && (
        <section>
          <h3 className="mb-2 text-[1.05rem]">Verification</h3>
          <div className="flex items-center gap-2">
            <StatusTag status={verification.verdict} />
            {verification.score != null && <span className="text-[13px] tabular-nums text-muted">score {verification.score.toFixed(2)}</span>}
          </div>
          {verification.score != null ? (
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 text-[12.5px]">
              <dt className="text-muted">Lexical support</dt><dd className="tabular-nums">{Math.round((verification.grounding ?? 0) * 100)}%</dd>
              <dt className="text-muted">Sentences cited</dt><dd className="tabular-nums">{verification.cited_sentences} of {(verification.cited_sentences ?? 0) + (verification.uncited_sentences ?? 0)}</dd>
              {!!verification.invalid_citations?.length && (<><dt className="text-maroon">Invalid citations</dt><dd className="text-maroon">{verification.invalid_citations.join(", ")}</dd></>)}
            </dl>
          ) : (
            <p className="mt-1.5 text-[12.5px] text-muted">{verification.detail}</p>
          )}
          {verification.method && <p className="mt-1.5 text-[11.5px] text-faint">Method: {verification.method}</p>}
        </section>
      )}

      {sources.length > 0 && (
        <section>
          <h3 className="mb-2 text-[1.05rem]">Sources</h3>
          <ol className="space-y-2">
            {sources.map((s) => (
              <li
                key={`${s.n}-${s.chunk_id ?? s.circular_id}`}
                id={`src-${s.n}`}
                className={clsx(
                  "rounded-md border p-2.5 text-[12.5px] transition-colors",
                  activeCite === s.n ? "border-gold bg-gold-soft" : "border-line bg-surface",
                )}
              >
                <button className="w-full text-left" onClick={() => onCite?.(s.n)}>
                  <div className="flex gap-2">
                    <span className="cite-chip !m-0 !align-baseline">{s.n}</span>
                    <span className="font-medium leading-snug text-text">{s.title}</span>
                  </div>
                  <div className="mt-1 pl-7 text-faint">
                    {[s.rbi_ref, s.published_at?.slice(0, 10)].filter(Boolean).join(" · ")}
                  </div>
                  {activeCite === s.n && <p className="mt-2 whitespace-pre-line pl-7 text-[12.5px] leading-relaxed text-muted">{s.text.slice(0, 900)}</p>}
                </button>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 pl-7 text-[11.5px] text-faint">
                  {s.dense_rank != null && <span title="Rank by semantic (vector) similarity">semantic #{s.dense_rank}</span>}
                  {s.bm25_rank != null && <span title="Rank by keyword (BM25) match">keyword #{s.bm25_rank}</span>}
                  {s.score != null && s.chunk_id != null && <span title="Reciprocal rank fusion score">fused {s.score.toFixed(4)}</span>}
                  <Link to={`/circulars/${s.circular_id}`} className="text-link hover:underline">Open circular</Link>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}

function StepDetail({ detail }: { detail: any }) {
  if (typeof detail !== "object") return <div className="mt-0.5 text-[12px] text-faint">{String(detail)}</div>;
  const entries = Object.entries(detail).filter(([, v]) => v !== null && v !== undefined && v !== "");
  if (!entries.length) return null;
  return (
    <div className="mt-1 space-y-0.5 text-[12px] text-faint">
      {entries.slice(0, 5).map(([k, v]) => (
        <div key={k} className="truncate" title={typeof v === "string" ? v : JSON.stringify(v)}>
          <span className="text-muted">{k.replace(/_/g, " ")}:</span> {typeof v === "string" ? v : JSON.stringify(v)}
        </div>
      ))}
    </div>
  );
}

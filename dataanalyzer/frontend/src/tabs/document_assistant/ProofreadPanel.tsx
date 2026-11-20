import { useState } from "react";
import type { AppliedResult, ExtractResult, Suggestion } from "./api";
import Downloads, { isDocx, textDownloads, type DownloadOption } from "./Downloads";

export type ProofreadState = {
  status: "idle" | "checking" | "ready" | "stopped" | "error";
  text: string;
  suggestions: Suggestion[];
  // Accepted replacement per suggestion id; null means rejected; missing means undecided.
  decisions: Record<string, string | null>;
  progress?: string;
  notices: string[];
  error?: { code: string; message: string };
  applied?: AppliedResult;
};

export const IDLE_PROOFREAD: ProofreadState = {
  status: "idle",
  text: "",
  suggestions: [],
  decisions: {},
  notices: [],
};

const CATEGORY_STYLE: Record<string, { label: string; line: string; dot: string }> = {
  spelling: { label: "Spelling", line: "decoration-red-500", dot: "bg-red-500" },
  grammar: { label: "Grammar", line: "decoration-pnb-gold", dot: "bg-pnb-gold" },
  punctuation: { label: "Punctuation", line: "decoration-sky-500", dot: "bg-sky-500" },
  style: { label: "Style", line: "decoration-violet-500", dot: "bg-violet-500" },
  clarity: { label: "Clarity", line: "decoration-pnb-maroon", dot: "bg-pnb-maroon" },
};

function styleFor(category: string) {
  return CATEGORY_STYLE[category] ?? CATEGORY_STYLE.grammar;
}

const CORRECTED_FILE_LABEL: Record<string, string> = {
  docx: "Word (original file, corrected)",
  xlsx: "Excel (original file, corrected)",
  csv: "CSV (corrected)",
  json: "JSON (corrected)",
};

function extension(filename: string): string {
  return filename.split(".").pop()?.toLowerCase() ?? "";
}

/** True if "Accept all" may apply this suggestion without asking. */
export function autoAcceptable(s: Suggestion): boolean {
  return s.applicable && s.replacements.length > 0 && (s.auto_accept ?? s.replacements.length === 1);
}

/** The accepted edits, ready to send to the server. */
export function acceptedEdits(p: ProofreadState) {
  return p.suggestions
    .filter((s) => typeof p.decisions[s.id] === "string")
    .map((s) => ({ start: s.start, end: s.end, replacement: p.decisions[s.id] as string }));
}

type Props = {
  proofread: ProofreadState;
  file: ExtractResult | null;
  applying: boolean;
  onDecide: (id: string, replacement: string | null) => void;
  onAcceptAll: () => void;
  onApply: () => void;
  onReview: () => void;
  onStop: () => void;
};

export default function ProofreadPanel(props: Props) {
  const { proofread: p, file, applying, onDecide, onAcceptAll, onApply, onReview, onStop } = props;
  const [openId, setOpenId] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const pending = p.suggestions.filter((s) => s.applicable && !(s.id in p.decisions));
  const autoPending = pending.filter(autoAcceptable).length;
  const needChoice = pending.length - autoPending;
  const accepted = acceptedEdits(p).length;

  const copy = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked by the browser; the text is still selectable.
    }
  };

  if (p.applied) {
    const applied = p.applied;
    const options: DownloadOption[] = [];
    if (applied.file_id && applied.filename) {
      const result = { file_id: applied.file_id, filename: applied.filename, warnings: applied.warnings };
      const ext = extension(applied.filename);
      options.push({ label: CORRECTED_FILE_LABEL[ext] ?? applied.filename, make: () => Promise.resolve(result) });
      // A data file comes back in its own format only (spec section 4).
      if (file?.kind !== "data") {
        options.push(...textDownloads(applied.text, file).filter((o) => o.label.startsWith("Text")));
      }
      for (const alt of applied.alternatives ?? []) {
        const altResult = { file_id: alt.file_id, filename: alt.filename, warnings: [] };
        options.push({ label: alt.label, make: () => Promise.resolve(altResult) });
      }
    } else {
      options.push(...textDownloads(applied.text, isDocx(file) ? null : file));
    }
    return (
      <div className="flex h-full flex-col">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium text-slate-700">Corrected text</span>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={onReview}
              className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:border-pnb-maroon hover:text-pnb-maroon"
            >
              Back to suggestions
            </button>
            <button
              type="button"
              onClick={() => copy(applied.text)}
              className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:border-pnb-maroon hover:text-pnb-maroon"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
        </div>
        <div className="min-h-64 flex-1 whitespace-pre-wrap rounded-lg border border-slate-200 bg-white p-5 text-sm leading-relaxed text-slate-800">
          {applied.text}
        </div>
        <div className="mt-4">
          <Downloads options={options} />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-slate-700">
          Suggestions
          {p.status === "ready" && (
            <span className="ml-2 font-normal text-slate-500">
              {p.suggestions.length} found · {accepted} accepted
            </span>
          )}
        </span>
        <div className="flex gap-2">
          {p.status === "checking" && (
            <button
              type="button"
              onClick={onStop}
              className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:border-pnb-maroon hover:text-pnb-maroon"
            >
              Stop
            </button>
          )}
          {p.status === "ready" && autoPending > 0 && (
            <button
              type="button"
              onClick={onAcceptAll}
              className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:border-pnb-maroon hover:text-pnb-maroon"
            >
              Accept all
            </button>
          )}
        </div>
      </div>

      <div
        aria-live="polite"
        className="min-h-64 flex-1 rounded-lg border border-slate-200 bg-white p-5 text-sm leading-relaxed text-slate-800"
      >
        {p.status === "idle" && (
          <p className="text-slate-400">Spelling, grammar and clarity suggestions will appear here.</p>
        )}
        {p.status === "checking" && (
          <p className="flex items-center gap-2 text-slate-500">
            <span className="h-2 w-2 animate-pulse rounded-full bg-pnb-gold" />
            {p.progress ?? "Checking…"}
          </p>
        )}
        {p.status === "stopped" && <p className="text-slate-400">Stopped.</p>}
        {p.status === "error" && p.error && (
          <div
            role="alert"
            className={`rounded-md px-3 py-2 ${
              p.error.code === "llm_unavailable" ? "bg-pnb-cream text-slate-700" : "bg-red-50 text-red-700"
            }`}
          >
            {p.error.message}
          </div>
        )}
        {p.status === "ready" && (
          <>
            {p.suggestions.length === 0 && (
              <p className="mb-4 rounded-md bg-pnb-cream px-3 py-2 text-slate-700">
                No issues found.
              </p>
            )}
            <AnnotatedText
              proofread={p}
              openId={openId}
              setOpenId={setOpenId}
              onDecide={(id, r) => {
                onDecide(id, r);
                setOpenId(null);
              }}
            />
          </>
        )}
      </div>

      {p.status === "ready" && needChoice > 0 && (
        <p className="mt-3 rounded-md bg-pnb-cream px-3 py-2 text-sm text-slate-700">
          {needChoice} suggestion{needChoice === 1 ? " needs" : "s need"} your choice. Click the
          underlined text to pick a correction; Accept all leaves these for you.
        </p>
      )}
      {p.status === "ready" && (
        <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
          {Object.entries(CATEGORY_STYLE).map(([key, c]) => (
            <span key={key} className="flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${c.dot}`} />
              {c.label}
            </span>
          ))}
        </div>
      )}
      {p.notices.map((n) => (
        <p key={n} className="mt-3 rounded-md bg-pnb-cream px-3 py-2 text-sm text-slate-700">
          {n}
        </p>
      ))}
      {p.status === "ready" && (
        <div className="mt-4">
          <button
            type="button"
            onClick={onApply}
            disabled={applying}
            className="rounded-md bg-pnb-maroon px-5 py-2 text-sm font-semibold text-white shadow-sm hover:bg-pnb-maroon-dark disabled:opacity-40"
          >
            {applying ? "Applying…" : `Apply ${accepted} change${accepted === 1 ? "" : "s"}`}
          </button>
        </div>
      )}
    </div>
  );
}

type AnnotatedProps = {
  proofread: ProofreadState;
  openId: string | null;
  setOpenId: (id: string | null) => void;
  onDecide: (id: string, replacement: string | null) => void;
};

function AnnotatedText({ proofread: p, openId, setOpenId, onDecide }: AnnotatedProps) {
  const parts: React.ReactNode[] = [];
  let pos = 0;
  for (const s of p.suggestions) {
    if (s.start < pos) continue; // the server never sends overlaps; be safe anyway
    if (s.start > pos) parts.push(p.text.slice(pos, s.start));
    const original = p.text.slice(s.start, s.end);
    const decision = p.decisions[s.id];
    const style = styleFor(s.category);
    if (typeof decision === "string") {
      parts.push(
        <button
          key={s.id}
          type="button"
          onClick={() => onDecide(s.id, null)}
          title={`Accepted. Click to undo (was "${original}").`}
          className="rounded bg-green-50 text-green-800 ring-1 ring-green-200"
        >
          {decision || "∅"}
        </button>,
      );
    } else if (decision === null) {
      parts.push(<span key={s.id}>{original}</span>);
    } else {
      parts.push(
        <span key={s.id} className="relative">
          <button
            type="button"
            aria-expanded={openId === s.id}
            onClick={() => setOpenId(openId === s.id ? null : s.id)}
            className={`underline decoration-2 underline-offset-4 ${style.line} ${
              s.applicable ? "" : "decoration-dotted opacity-70"
            } hover:bg-slate-50`}
          >
            {original || "‸"}
          </button>
          {openId === s.id && (
            <Popover suggestion={s} label={style.label} onDecide={onDecide} onClose={() => setOpenId(null)} />
          )}
        </span>,
      );
    }
    pos = s.end;
  }
  if (pos < p.text.length) parts.push(p.text.slice(pos));
  return <div className="whitespace-pre-wrap">{parts}</div>;
}

type PopoverProps = {
  suggestion: Suggestion;
  label: string;
  onDecide: (id: string, replacement: string | null) => void;
  onClose: () => void;
};

function Popover({ suggestion: s, label, onDecide, onClose }: PopoverProps) {
  return (
    <span
      role="dialog"
      onKeyDown={(e) => e.key === "Escape" && onClose()}
      className="absolute left-0 top-full z-10 mt-2 block w-72 rounded-lg border border-slate-200 bg-white p-4 text-left text-sm whitespace-normal shadow-lg"
    >
      <span className="block text-xs font-semibold uppercase tracking-wide text-slate-500">
        {label}
      </span>
      <span className="mt-1 block text-slate-700">{s.message}</span>
      {!s.applicable && (
        <span className="mt-2 block text-xs text-slate-500">
          This text is inside a link, field or several paragraphs, so the fix cannot be applied
          automatically.
        </span>
      )}
      <span className="mt-3 flex flex-wrap gap-2">
        {s.applicable &&
          s.replacements.map((r, i) => (
            <button
              key={r}
              type="button"
              onClick={() => onDecide(s.id, r)}
              title={i === 0 && s.recommended ? "Recommended for this sentence" : undefined}
              className="rounded-md bg-pnb-maroon px-3 py-1 text-sm font-medium text-white hover:bg-pnb-maroon-dark"
            >
              {r || "(remove)"}
              {i === 0 && s.recommended && (
                <span className="ml-1.5 rounded bg-pnb-gold px-1 text-[10px] font-semibold uppercase text-slate-900">
                  Recommended
                </span>
              )}
            </button>
          ))}
        <button
          type="button"
          onClick={() => onDecide(s.id, null)}
          className="rounded-md border border-slate-200 px-3 py-1 text-sm text-slate-600 hover:border-pnb-maroon hover:text-pnb-maroon"
        >
          {s.applicable ? "Reject" : "Dismiss"}
        </button>
      </span>
    </span>
  );
}

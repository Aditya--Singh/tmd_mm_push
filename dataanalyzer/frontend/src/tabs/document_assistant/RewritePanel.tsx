import { useState } from "react";
import type { ExtractResult, SourceParagraph } from "./api";
import Downloads, { isDocx, textDownloads } from "./Downloads";

export type RewriteState = {
  status: "idle" | "streaming" | "done" | "stopped" | "error";
  source: SourceParagraph[];
  // Rewritten paragraphs, by source index; null until that paragraph's section finishes.
  output: (string | null)[];
  // The section being streamed right now.
  live: { paragraphs: number[]; text: string } | null;
  // The final, editable text (set when the stream ends).
  text: string;
  progress?: string;
  notices: string[];
  error?: { code: string; message: string };
};

export const IDLE_REWRITE: RewriteState = {
  status: "idle",
  source: [],
  output: [],
  live: null,
  text: "",
  notices: [],
};

/** Joined text: rewritten paragraphs where ready, the original elsewhere, with the
 * original line breaks between paragraphs. */
export function finalText(r: RewriteState): string {
  return r.source
    .map((p, i) => (i === 0 ? "" : (p.before ?? "\n\n")) + (r.output[i] ?? p.text))
    .join("");
}

type Props = {
  rewrite: RewriteState;
  file: ExtractResult | null;
  onEdit: (text: string) => void;
  onStop: () => void;
};

export default function RewritePanel({ rewrite, file, onEdit, onStop }: Props) {
  const [copied, setCopied] = useState(false);
  const streaming = rewrite.status === "streaming";
  const editable = rewrite.status === "done" || rewrite.status === "stopped";

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(rewrite.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked by the browser; the text is still selectable.
    }
  };

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">Rewritten text</span>
        <div className="flex gap-2">
          {streaming && (
            <button
              type="button"
              onClick={onStop}
              className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:border-pnb-maroon hover:text-pnb-maroon"
            >
              Stop
            </button>
          )}
          {editable && rewrite.text && (
            <button
              type="button"
              onClick={copy}
              className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:border-pnb-maroon hover:text-pnb-maroon"
            >
              {copied ? "Copied" : "Copy"}
            </button>
          )}
        </div>
      </div>

      {editable ? (
        <textarea
          aria-label="Rewritten text"
          value={rewrite.text}
          onChange={(e) => onEdit(e.target.value)}
          className="min-h-96 w-full flex-1 resize-y rounded-lg border border-slate-200 bg-white p-5 text-sm leading-relaxed text-slate-800 focus:border-pnb-maroon focus:outline-none focus:ring-2 focus:ring-pnb-gold/30"
        />
      ) : (
        <div
          aria-live="polite"
          className="min-h-64 flex-1 space-y-4 rounded-lg border border-slate-200 bg-white p-5 text-sm leading-relaxed text-slate-800"
        >
          {rewrite.status === "idle" && (
            <p className="text-slate-400">Your rewritten text will appear here.</p>
          )}
          {streaming && <StreamingView rewrite={rewrite} />}
          {rewrite.status === "error" && rewrite.error && (
            <div
              role="alert"
              className={`rounded-md px-3 py-2 ${
                rewrite.error.code === "llm_unavailable"
                  ? "bg-pnb-cream text-slate-700"
                  : "bg-red-50 text-red-700"
              }`}
            >
              {rewrite.error.message}
            </div>
          )}
        </div>
      )}

      {rewrite.status === "stopped" && (
        <p className="mt-2 text-xs text-slate-500">
          Stopped. Paragraphs not yet rewritten are shown as in the original.
        </p>
      )}
      {rewrite.notices.map((n) => (
        <p key={n} className="mt-3 rounded-md bg-pnb-cream px-3 py-2 text-sm text-slate-700">
          {n}
        </p>
      ))}
      {editable && rewrite.text && (
        <div className="mt-4 space-y-2">
          {isDocx(file) && (
            <p className="text-xs text-slate-500">
              To save into the original Word file, keep one blank line between paragraphs and do
              not add or remove paragraphs.
            </p>
          )}
          <Downloads options={textDownloads(rewrite.text, file)} />
        </div>
      )}
    </div>
  );
}

function StreamingView({ rewrite }: { rewrite: RewriteState }) {
  const { source, output, live } = rewrite;
  const blocks: { key: string; text: string; muted: boolean }[] = [];
  source.forEach((p, i) => {
    if (output[i] != null) {
      blocks.push({ key: `p${i}`, text: output[i]!, muted: false });
    } else if (live && live.paragraphs[0] === i) {
      blocks.push({ key: `live${i}`, text: live.text, muted: false });
    } else if (!p.editable && (live === null || i < live.paragraphs[0])) {
      blocks.push({ key: `p${i}`, text: p.text, muted: true });
    }
  });
  const waiting = !live || live.text === "";
  return (
    <>
      {blocks.map((b) => (
        <p key={b.key} className={`whitespace-pre-wrap ${b.muted ? "text-slate-400" : ""}`}>
          {b.text}
        </p>
      ))}
      {waiting ? (
        <p className="flex items-center gap-2 text-slate-500">
          <span className="h-2 w-2 animate-pulse rounded-full bg-pnb-gold" />
          {rewrite.progress ?? "Thinking…"}
        </p>
      ) : (
        <span className="inline-block h-4 w-1.5 animate-pulse bg-pnb-gold align-middle" />
      )}
    </>
  );
}

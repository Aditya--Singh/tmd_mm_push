import { useState } from "react";
import Markdown, { toPlainText } from "./Markdown";

export type ResultState = {
  status: "idle" | "streaming" | "done" | "stopped" | "error";
  text: string;
  progress?: string;
  error?: { code: string; message: string };
};

type Props = { result: ResultState; onStop: () => void };

export default function ResultPanel({ result, onStop }: Props) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(toPlainText(result.text));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked by the browser; the text is still selectable.
    }
  };

  const streaming = result.status === "streaming";

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">Summary</span>
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
          {result.text && !streaming && (
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

      <div
        aria-live="polite"
        className="min-h-64 flex-1 rounded-lg border border-slate-200 bg-white p-5 text-sm leading-relaxed text-slate-800"
      >
        {result.status === "idle" && !result.text && (
          <p className="text-slate-400">Your summary will appear here.</p>
        )}
        {streaming && !result.text && (
          <p className="flex items-center gap-2 text-slate-500">
            <span className="h-2 w-2 animate-pulse rounded-full bg-pnb-gold" />
            {result.progress ?? "Thinking…"}
          </p>
        )}
        {result.text && <Markdown text={result.text} />}
        {streaming && result.text && (
          <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-pnb-gold align-middle" />
        )}
        {result.status === "stopped" && (
          <p className="mt-3 text-xs text-slate-400">Stopped.</p>
        )}
        {result.status === "error" && result.error && (
          <div
            role="alert"
            className={`mt-3 rounded-md px-3 py-2 ${
              result.error.code === "llm_unavailable"
                ? "bg-pnb-cream text-slate-700"
                : "bg-red-50 text-red-700"
            }`}
          >
            {result.error.message}
          </div>
        )}
      </div>
    </div>
  );
}

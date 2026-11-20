import { useEffect, useRef, useState } from "react";
import type { ChatHistoryTurn, DataTable, ExtractResult } from "./api";
import Markdown, { toPlainText } from "./Markdown";

export type ChatTurn = {
  question: string;
  status: "thinking" | "done" | "stopped" | "error";
  progress?: string;
  // The operation the server ran, sent back with follow-up questions.
  operation?: Record<string, unknown>;
  table?: DataTable;
  // The answer as it streams, before it is checked against the computed figures.
  live?: string;
  // The checked answer.
  answer?: string;
  // A plain message shown instead of an answer (question not supported, or not checked).
  message?: string;
  error?: { code: string; message: string };
};

export type ChatState = { turns: ChatTurn[] };

export const IDLE_CHAT: ChatState = { turns: [] };

/** Earlier completed turns, as the server expects them with a new question. */
export function chatHistory(chat: ChatState): ChatHistoryTurn[] {
  return chat.turns
    .filter((t) => t.status === "done")
    .map((t) => ({ question: t.question, operation: t.operation ?? null, answer: t.answer ?? null }));
}

/** A conversation cut off by a page refresh cannot resume; show the last turn as stopped. */
export function restoreChat(chat: ChatState | undefined): ChatState {
  if (!chat) return IDLE_CHAT;
  return {
    turns: chat.turns.map((t) =>
      t.status === "thinking" ? { ...t, status: "stopped", live: undefined, progress: undefined } : t,
    ),
  };
}

const EXAMPLES = [
  "What is the total outstanding by branch?",
  "Which 5 loans have the highest sanctioned amount?",
  "How many accounts are in each zone?",
];

type Props = {
  chat: ChatState;
  file: ExtractResult | null;
  onAsk: (question: string) => void;
  onStop: () => void;
  onNewConversation: () => void;
};

export default function DataChatPanel({ chat, file, onAsk, onStop, onNewConversation }: Props) {
  const [question, setQuestion] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const thinking = chat.turns.some((t) => t.status === "thinking");
  const ready = file?.kind === "data";

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [chat]);

  const submit = () => {
    const q = question.trim();
    if (!q || thinking || !ready) return;
    onAsk(q);
    setQuestion("");
  };

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">Conversation</span>
        {chat.turns.length > 0 && !thinking && (
          <button
            type="button"
            onClick={onNewConversation}
            className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:border-pnb-maroon hover:text-pnb-maroon"
          >
            New conversation
          </button>
        )}
      </div>

      <div
        ref={scrollRef}
        aria-live="polite"
        className="min-h-64 max-h-[40rem] flex-1 space-y-6 overflow-y-auto rounded-lg border border-slate-200 bg-white p-5 text-sm leading-relaxed text-slate-800"
      >
        {chat.turns.length === 0 && <EmptyState file={file} onPick={setQuestion} />}
        {chat.turns.map((t, i) => (
          <Turn key={i} turn={t} />
        ))}
      </div>

      <form
        className="mt-4"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <label className="block">
          <span className="sr-only">Your question</span>
          <textarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            disabled={!ready}
            rows={2}
            maxLength={2000}
            placeholder={ready ? "Ask a question about this file…" : "Upload a data file first"}
            className="w-full resize-y rounded-lg border border-slate-200 p-3 text-sm focus:border-pnb-maroon focus:outline-none focus:ring-2 focus:ring-pnb-gold/30 disabled:bg-slate-50"
          />
        </label>
        <div className="mt-3 flex items-center gap-3">
          {thinking ? (
            <button
              type="button"
              onClick={onStop}
              className="rounded-md border border-slate-200 px-5 py-2 text-sm text-slate-600 hover:border-pnb-maroon hover:text-pnb-maroon"
            >
              Stop
            </button>
          ) : (
            <button
              type="submit"
              disabled={!ready || !question.trim()}
              className="rounded-md bg-pnb-maroon px-6 py-2 text-sm font-semibold text-white shadow-sm hover:bg-pnb-maroon-dark focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pnb-gold disabled:cursor-not-allowed disabled:opacity-40"
            >
              Ask
            </button>
          )}
          <span className="text-xs text-slate-500">
            Figures are computed from the file, not by the language model.
          </span>
        </div>
      </form>
    </div>
  );
}

function EmptyState({ file, onPick }: { file: ExtractResult | null; onPick: (q: string) => void }) {
  if (!file) {
    return <p className="text-slate-400">Upload an Excel, CSV or JSON file, then ask questions about it.</p>;
  }
  if (file.kind !== "data") {
    return (
      <p className="rounded-md bg-pnb-cream px-3 py-2 text-slate-700">
        Ask about data works with Excel, CSV and JSON files. For documents, use Summarize, Rewrite
        or Proofread.
      </p>
    );
  }
  return (
    <div className="text-slate-500">
      <p>Ask about totals, counts, averages, highest and lowest values, or rows that match. For example:</p>
      <ul className="mt-3 space-y-2">
        {EXAMPLES.map((q) => (
          <li key={q}>
            <button
              type="button"
              onClick={() => onPick(q)}
              className="text-left text-pnb-maroon underline-offset-2 hover:underline"
            >
              {q}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function tableAsText(table: DataTable): string {
  return [table.description, table.columns.join("\t"), ...table.rows.map((r) => r.join("\t"))].join("\n");
}

function Turn({ turn: t }: { turn: ChatTurn }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    const parts = [t.answer ? toPlainText(t.answer) : t.message, t.table && tableAsText(t.table)];
    try {
      await navigator.clipboard.writeText(parts.filter(Boolean).join("\n\n"));
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard can be blocked by the browser; the text is still selectable.
    }
  };

  return (
    <div>
      <div className="flex justify-end">
        <p className="max-w-[85%] whitespace-pre-wrap rounded-lg bg-pnb-cream px-4 py-2 text-slate-800">
          {t.question}
        </p>
      </div>

      <div className="mt-3 space-y-3">
        {t.status === "thinking" && t.live === undefined && (
          <p className="flex items-center gap-2 text-slate-500">
            <span className="h-2 w-2 animate-pulse rounded-full bg-pnb-gold" />
            {t.progress ?? "Thinking…"}
          </p>
        )}
        {t.live !== undefined && (
          <div>
            <p className="mb-1 text-xs text-slate-400">Checking the figures against the result…</p>
            <div className="whitespace-pre-wrap text-slate-400">{t.live}</div>
          </div>
        )}
        {t.answer && <Markdown text={t.answer} />}
        {t.message && <p className="rounded-md bg-pnb-cream px-3 py-2 text-slate-700">{t.message}</p>}
        {t.status === "stopped" && <p className="text-xs text-slate-400">Stopped.</p>}
        {t.status === "error" && t.error && (
          <div
            role="alert"
            className={`rounded-md px-3 py-2 ${
              t.error.code === "llm_unavailable" ? "bg-pnb-cream text-slate-700" : "bg-red-50 text-red-700"
            }`}
          >
            {t.error.message}
          </div>
        )}
        {t.table && <ResultTable table={t.table} />}
        {t.status === "done" && (t.answer || t.table) && (
          <button
            type="button"
            onClick={copy}
            className="rounded-md border border-slate-200 px-3 py-1 text-xs text-slate-600 hover:border-pnb-maroon hover:text-pnb-maroon"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        )}
      </div>
    </div>
  );
}

function ResultTable({ table }: { table: DataTable }) {
  return (
    <div>
      <p className="mb-2 text-xs text-slate-500">{table.description}</p>
      {table.total_rows > 0 && (
        <div className="max-h-80 overflow-auto rounded-lg border border-slate-200">
          <table className="min-w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-50 text-slate-600">
              <tr>
                {table.columns.map((c, j) => (
                  <th
                    key={j}
                    className={`whitespace-nowrap px-3 py-2 font-medium ${
                      table.kinds[j] === "number" ? "text-right" : ""
                    }`}
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {table.rows.map((row, i) => (
                <tr key={i} className="border-t border-slate-100">
                  {row.map((v, j) => (
                    <td
                      key={j}
                      className={`whitespace-nowrap px-3 py-1.5 text-slate-700 ${
                        table.kinds[j] === "number" ? "text-right tabular-nums" : ""
                      }`}
                    >
                      {v}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {table.total_rows > table.rows.length && (
        <p className="mt-1 text-xs text-slate-500">
          Showing the first {table.rows.length.toLocaleString("en-IN")} of{" "}
          {table.total_rows.toLocaleString("en-IN")} rows.
        </p>
      )}
    </div>
  );
}

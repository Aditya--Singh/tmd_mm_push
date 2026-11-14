import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Source } from "../lib/types";

/** Markdown renderer that turns [n] citation markers into interactive chips linked to the source list. */
export function Markdown({
  text,
  sources = [],
  activeCite,
  onCite,
  streaming,
}: {
  text: string;
  sources?: Source[];
  activeCite?: number | null;
  onCite?: (n: number) => void;
  streaming?: boolean;
}) {
  const prepared = useMemo(() => text.replace(/\[(\d{1,2})\](?!\()/g, (_m, n) => `[\\[${n}\\]](#cite-${n})`), [text]);
  const byN = useMemo(() => Object.fromEntries(sources.map((s) => [s.n, s])), [sources]);

  return (
    <div className={`prose-reg ${streaming ? "caret" : ""}`}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children }) => {
            if (href?.startsWith("#cite-")) {
              const n = Number(href.slice(6));
              const src = byN[n];
              return (
                <button
                  type="button"
                  className="cite-chip"
                  data-active={activeCite === n}
                  title={src ? `${src.title}${src.rbi_ref ? ` — ${src.rbi_ref}` : ""}` : `Source ${n} (not in the retrieved set)`}
                  onClick={() => onCite?.(n)}
                >
                  {n}
                </button>
              );
            }
            return (
              <a href={href} target="_blank" rel="noreferrer noopener">
                {children}
              </a>
            );
          },
        }}
      >
        {prepared}
      </ReactMarkdown>
    </div>
  );
}

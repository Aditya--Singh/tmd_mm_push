import type { ReactNode } from "react";

/*
 * A deliberately small Markdown renderer for model output: paragraphs, headings, bullet and
 * numbered lists, **bold** and *italic*. It builds React elements only (never innerHTML), so
 * anything else the model writes, including HTML, is shown as plain text.
 */

type Block =
  | { type: "p"; lines: string[] }
  | { type: "h"; text: string }
  | { type: "ul" | "ol"; items: string[] };

const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const HEADING = /^\s*#{1,6}\s+(.*)$/;
const RULE = /^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/;
const INLINE = /(\*\*[^*\n]+\*\*|__[^_\n]+__|\*[^*\s][^*\n]*\*)/g;

function parse(text: string): Block[] {
  const blocks: Block[] = [];
  const last = () => blocks[blocks.length - 1];
  for (const line of text.split("\n")) {
    let m: RegExpMatchArray | null;
    if (!line.trim() || RULE.test(line)) {
      blocks.push({ type: "p", lines: [] }); // ends the current block
    } else if ((m = line.match(HEADING))) {
      blocks.push({ type: "h", text: m[1] });
    } else if ((m = line.match(BULLET)) || (m = line.match(NUMBERED))) {
      const type = BULLET.test(line) ? "ul" : "ol";
      const prev = last();
      if (prev && prev.type === type) prev.items.push(m[1]);
      else blocks.push({ type, items: [m[1]] });
    } else {
      const prev = last();
      if (prev && prev.type === "p") prev.lines.push(line.trim());
      else blocks.push({ type: "p", lines: [line.trim()] });
    }
  }
  return blocks.filter((b) => b.type !== "p" || b.lines.length > 0);
}

function inline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, i) => {
    if ((part.startsWith("**") && part.endsWith("**")) || (part.startsWith("__") && part.endsWith("__"))) {
      if (part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={i}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}

export default function Markdown({ text }: { text: string }) {
  return (
    <div className="space-y-3">
      {parse(text).map((b, i) => {
        if (b.type === "p") return <p key={i}>{inline(b.lines.join(" "))}</p>;
        if (b.type === "h") {
          return (
            <p key={i} className="font-semibold text-slate-900">
              {inline(b.text)}
            </p>
          );
        }
        const List = b.type;
        return (
          <List
            key={i}
            className={`space-y-1 pl-5 ${List === "ul" ? "list-disc marker:text-pnb-gold" : "list-decimal"}`}
          >
            {b.items.map((item, j) => (
              <li key={j}>{inline(item)}</li>
            ))}
          </List>
        );
      })}
    </div>
  );
}

/** The same text without Markdown markers, for pasting into Word or email. */
export function toPlainText(text: string): string {
  return text
    .split("\n")
    .map((line) => {
      if (RULE.test(line)) return "";
      const bullet = line.match(BULLET);
      if (bullet) return `• ${bullet[1]}`;
      const heading = line.match(HEADING);
      return heading ? heading[1] : line;
    })
    .join("\n")
    .replace(/\*\*([^*\n]+)\*\*/g, "$1")
    .replace(/__([^_\n]+)__/g, "$1")
    .replace(/\*([^*\s][^*\n]*)\*/g, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

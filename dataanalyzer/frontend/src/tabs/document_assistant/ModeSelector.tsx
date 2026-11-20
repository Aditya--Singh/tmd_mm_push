export type Mode = "proofread" | "rewrite" | "summarize" | "draft" | "data";

export const MODES: { id: Mode; label: string; ready: boolean }[] = [
  { id: "proofread", label: "Proofread", ready: true },
  { id: "rewrite", label: "Rewrite", ready: true },
  { id: "summarize", label: "Summarize", ready: true },
  { id: "draft", label: "Draft", ready: false },
  { id: "data", label: "Ask about data", ready: true },
];

type Props = { active: Mode; onSelect: (mode: Mode) => void; disabled?: boolean };

export default function ModeSelector({ active, onSelect, disabled = false }: Props) {
  return (
    <div role="radiogroup" aria-label="Mode" className="flex flex-wrap gap-2">
      {MODES.map((m) => {
        const selected = m.id === active;
        return (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={!m.ready || (disabled && !selected)}
            onClick={() => onSelect(m.id)}
            className={`rounded-full border px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pnb-gold ${
              selected
                ? "border-pnb-maroon bg-pnb-maroon text-white"
                : m.ready
                  ? "border-slate-200 bg-white text-slate-700 hover:border-pnb-maroon hover:text-pnb-maroon"
                  : "cursor-not-allowed border-slate-100 bg-slate-50 text-slate-400"
            }`}
          >
            {m.label}
            {!m.ready && <span className="ml-2 text-[10px] uppercase tracking-wide">Soon</span>}
          </button>
        );
      })}
    </div>
  );
}

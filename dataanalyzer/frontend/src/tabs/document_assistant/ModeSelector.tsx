import { TOOLS, type ToolId } from "../../tools";

export type Mode = ToolId;

type Props = { active: Mode; onSelect: (mode: Mode) => void; disabled?: boolean };

export default function ModeSelector({ active, onSelect, disabled = false }: Props) {
  return (
    <div role="radiogroup" aria-label="Mode" className="flex flex-wrap gap-2">
      {TOOLS.map((m) => {
        const selected = m.id === active;
        return (
          <button
            key={m.id}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled && !selected}
            onClick={() => onSelect(m.id)}
            className={`rounded-full border px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-pnb-gold ${
              selected
                ? "border-pnb-maroon bg-pnb-maroon text-white"
                : "border-slate-200 bg-white text-slate-700 hover:border-pnb-maroon hover:text-pnb-maroon"
            }`}
          >
            {m.label}
          </button>
        );
      })}
    </div>
  );
}

import { useRef } from "react";
import { TABS, type TabId } from "../tabs";

type Props = { active: TabId; onSelect: (id: TabId) => void };

export default function TabBar({ active, onSelect }: Props) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const onKeyDown = (e: React.KeyboardEvent, index: number) => {
    let next = index;
    if (e.key === "ArrowRight") next = (index + 1) % TABS.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TABS.length - 1;
    else return;
    e.preventDefault();
    onSelect(TABS[next].id);
    refs.current[next]?.focus();
  };

  return (
    <nav className="border-b border-slate-200 bg-white">
      <div role="tablist" aria-label="Tools" className="mx-auto flex max-w-6xl gap-2 px-6">
        {TABS.map((tab, i) => {
          const selected = tab.id === active;
          return (
            <button
              key={tab.id}
              id={`tab-${tab.id}`}
              ref={(el) => {
                refs.current[i] = el;
              }}
              role="tab"
              aria-selected={selected}
              aria-controls={`panel-${tab.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => onSelect(tab.id)}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={`-mb-px border-b-[3px] px-4 py-4 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-4px] focus-visible:outline-pnb-gold ${
                selected
                  ? "border-pnb-gold text-pnb-maroon"
                  : "border-transparent text-slate-500 hover:border-slate-200 hover:text-pnb-maroon"
              }`}
            >
              {tab.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}

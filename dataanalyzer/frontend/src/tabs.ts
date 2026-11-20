export type TabId = "document-assistant" | "circular-analyzer" | "coming-soon";

export const TABS: { id: TabId; label: string }[] = [
  { id: "document-assistant", label: "Document Assistant" },
  { id: "circular-analyzer", label: "Circular Analyzer" },
  { id: "coming-soon", label: "Coming Soon" },
];

export function tabFromHash(hash: string): TabId {
  const id = hash.replace(/^#\/?/, "");
  return TABS.some((t) => t.id === id) ? (id as TabId) : TABS[0].id;
}

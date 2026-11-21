/**
 * The tools of the Data Analyzer.
 *
 * This is the one list of them: the hub draws these in its own rail, and the app
 * uses the same names for the buttons of the mode selector, so the rail and the
 * app can never disagree about what the tool can do.
 *
 * The id is also the route of the tool (`/#/proofread`), so that the hub may
 * send the person straight to one of them.
 */
export type ToolId = "proofread" | "rewrite" | "summarize" | "data";

export const TOOLS: { id: ToolId; label: string }[] = [
  { id: "proofread", label: "Proofread" },
  { id: "rewrite", label: "Rewrite" },
  { id: "summarize", label: "Summarize" },
  { id: "data", label: "Ask about data" },
];

export const DEFAULT_TOOL: ToolId = "proofread";

/**
 * The tool a fragment names, or the first one when the fragment names none.
 */
export function toolFromHash(hash: string): ToolId {
  const id = hash.replace(/^#\/?/, "").toLowerCase();

  return TOOLS.some((tool) => tool.id === id) ? (id as ToolId) : DEFAULT_TOOL;
}

/**
 * The tool a path names.
 *
 * The hub sends a path like `/#/proofread`, so everything up to the name is
 * dropped, and only the name itself is kept.
 */
export function toolFromPath(path: string): ToolId | null {
  const id = String(path ?? "")
    .toLowerCase()
    .split(/[^a-z0-9-]+/)
    .filter(Boolean)
    .pop();

  if (!id) return null;

  return TOOLS.some((tool) => tool.id === id) ? (id as ToolId) : null;
}

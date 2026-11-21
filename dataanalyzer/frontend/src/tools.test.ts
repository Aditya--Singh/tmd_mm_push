import { describe, expect, it } from "vitest";

import { DEFAULT_TOOL, TOOLS, toolFromHash, toolFromPath } from "./tools";

describe("the tools of the analyzer", () => {
  it("are the four the hub draws in its rail", () => {
    expect(TOOLS.map((tool) => tool.id)).toEqual([
      "proofread",
      "rewrite",
      "summarize",
      "data",
    ]);

    expect(TOOLS.map((tool) => tool.label)).toEqual([
      "Proofread",
      "Rewrite",
      "Summarize",
      "Ask about data",
    ]);
  });

  it("do not name the screens that were taken out", () => {
    const ids = TOOLS.map((tool) => tool.id);

    expect(ids).not.toContain("document-assistant");
    expect(ids).not.toContain("circular-analyzer");
    expect(ids).not.toContain("coming-soon");
  });
});

describe("the route of a tool", () => {
  it("names the tool of the fragment", () => {
    expect(toolFromHash("#/proofread")).toBe("proofread");
    expect(toolFromHash("#/rewrite")).toBe("rewrite");
    expect(toolFromHash("#/summarize")).toBe("summarize");
    expect(toolFromHash("#/data")).toBe("data");
  });

  it("falls back to the first tool", () => {
    expect(toolFromHash("")).toBe(DEFAULT_TOOL);
    expect(toolFromHash("#/circular-analyzer")).toBe(DEFAULT_TOOL);
    expect(toolFromHash("#/nonsense")).toBe(DEFAULT_TOOL);
  });
});

describe("the path the hub sends", () => {
  it("names the tool, whatever it carries around it", () => {
    // This is the form the manifest uses.
    expect(toolFromPath("/#/proofread")).toBe("proofread");
    expect(toolFromPath("/#/rewrite")).toBe("rewrite");
    expect(toolFromPath("/#/summarize")).toBe("summarize");
    expect(toolFromPath("/#/data")).toBe("data");

    // And the plainer forms.
    expect(toolFromPath("proofread")).toBe("proofread");
    expect(toolFromPath("#/proofread")).toBe("proofread");
    expect(toolFromPath("/proofread")).toBe("proofread");
  });

  it("is refused when it names no tool of this app", () => {
    expect(toolFromPath("/#/document-assistant")).toBeNull();
    expect(toolFromPath("/#/circular-analyzer")).toBeNull();
    expect(toolFromPath("")).toBeNull();
    expect(toolFromPath(undefined as unknown as string)).toBeNull();
  });
});

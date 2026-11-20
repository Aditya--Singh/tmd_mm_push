import { describe, expect, it } from "vitest";

import { isAllowedOrigin, normaliseOrigins, ticketFrom } from "./hub";

describe("the bridge to the hub", () => {
  it("takes the ticket the hub sends", () => {
    expect(
      ticketFrom({ type: "hubint:auth", payload: { ticket: "abc", username: "analyst" } }),
    ).toBe("abc");
  });

  it("ignores every other message", () => {
    expect(ticketFrom({ type: "hubint:logout" })).toBeNull();
    expect(ticketFrom({ type: "hubint:route" })).toBeNull();
    expect(ticketFrom({ type: "hubint:auth" })).toBeNull();
    expect(ticketFrom({ type: "hubint:auth", payload: {} })).toBeNull();
    expect(ticketFrom({ type: "hubint:auth", payload: { ticket: "" } })).toBeNull();
    expect(ticketFrom(null)).toBeNull();
    expect(ticketFrom(undefined)).toBeNull();
    expect(ticketFrom("ticket")).toBeNull();
    expect(ticketFrom(42)).toBeNull();
  });
});

describe("the allow-list of origins", () => {
  it("keeps the origins that are given", () => {
    expect(normaliseOrigins("http://localhost:5174, http://127.0.0.1:5174/")).toEqual([
      "http://localhost:5174",
      "http://127.0.0.1:5174",
    ]);
  });

  it("only lets the hub's own address through", () => {
    const allowed = normaliseOrigins("http://localhost:5174");

    expect(isAllowedOrigin("http://localhost:5174", allowed)).toBe(true);
    expect(isAllowedOrigin("http://localhost:5174/", allowed)).toBe(true);
    expect(isAllowedOrigin("http://evil.example", allowed)).toBe(false);
    expect(isAllowedOrigin("", allowed)).toBe(false);
  });
});

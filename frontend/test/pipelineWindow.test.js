import assert from "node:assert/strict";
import { test } from "node:test";

import {
    cutoffDate,
    DEFAULT_DAYS,
    MAX_DAYS,
    WINDOWS,
} from "../src/components/pipelineWindow.js";

test("the window may be as long as ninety days", () => {
    assert.equal(MAX_DAYS, 90);
});

test("the longest window on offer is ninety days", () => {
    const longest = Math.max(...WINDOWS.map((window) => window.days));

    assert.equal(longest, 90);
});

test("every window is inside the limit", () => {
    for (const window of WINDOWS) {
        assert.ok(window.days >= 1, `${window.days} is not a window`);
        assert.ok(window.days <= MAX_DAYS, `${window.days} is too long`);
    }
});

test("the windows are in order and none is repeated", () => {
    const days = WINDOWS.map((window) => window.days);

    assert.deepEqual([...days].sort((a, b) => a - b), days);
    assert.equal(new Set(days).size, days.length);
});

test("thirty days is the window to begin with", () => {
    assert.equal(DEFAULT_DAYS, 30);
    assert.ok(
        WINDOWS.some((window) => window.days === DEFAULT_DAYS),
        "the default window is not on offer",
    );
});

test("the cut-off is the day the window starts at", () => {
    const today = new Date(2026, 10, 12);

    assert.equal(cutoffDate(30, today), "13 Oct 2026");
    assert.equal(cutoffDate(1, today), "11 Nov 2026");
    assert.equal(cutoffDate(90, today), "14 Aug 2026");
});

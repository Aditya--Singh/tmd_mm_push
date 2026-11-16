import assert from "node:assert/strict";
import { test } from "node:test";

import { writtenDate } from "../src/components/writtenDate.js";

test("a date is written the same way on every machine", () => {
    // The way a browser writes a date depends on the language data it carries,
    // so the date is written out by hand.
    assert.equal(writtenDate(new Date(2026, 9, 13)), "13 Oct 2026");
    assert.equal(writtenDate(new Date(2026, 0, 1)), "01 Jan 2026");
    assert.equal(writtenDate(new Date(2026, 11, 31)), "31 Dec 2026");
});

test("a date given as a string is written as well", () => {
    assert.equal(writtenDate("2026-10-13"), "13 Oct 2026");
});

test("a date that cannot be read is left empty", () => {
    assert.equal(writtenDate("not a date"), "");
});

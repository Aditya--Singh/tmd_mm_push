import assert from "node:assert/strict";
import { test } from "node:test";

import {
    readSidebarCollapsed,
    writeSidebarCollapsed,
} from "../src/session/sidebar.js";

function createFakeStorage() {
    const map = new Map();

    return {
        getItem: (key) => (map.has(key) ? map.get(key) : null),
        setItem: (key, value) => map.set(key, String(value)),
        removeItem: (key) => map.delete(key),
    };
}

test("the rail starts expanded", () => {
    const storage = createFakeStorage();

    assert.equal(readSidebarCollapsed(storage), false);
});

test("the collapsed state is remembered", () => {
    const storage = createFakeStorage();

    writeSidebarCollapsed(true, storage);

    assert.equal(readSidebarCollapsed(storage), true);
});

test("the expanded state is remembered too", () => {
    const storage = createFakeStorage();

    writeSidebarCollapsed(true, storage);
    writeSidebarCollapsed(false, storage);

    assert.equal(readSidebarCollapsed(storage), false);
});

test("an unavailable storage does not break the rail", () => {
    const storage = {
        getItem: () => {
            throw new Error("storage is not available");
        },
        setItem: () => {
            throw new Error("storage is not available");
        },
    };

    assert.equal(readSidebarCollapsed(storage), false);
    assert.doesNotThrow(() => writeSidebarCollapsed(true, storage));
});

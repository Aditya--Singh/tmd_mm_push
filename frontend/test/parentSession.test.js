import assert from "node:assert/strict";
import { test } from "node:test";

import {
    MESSAGE_AUTH,
    MESSAGE_LOGOUT,
    MESSAGE_LOGOUT_ACK,
    MESSAGE_READY,
    createParentSessionBridge,
    isAllowedOrigin,
    normaliseOrigins,
} from "../src/session/parentSession.js";
import { readSession } from "../src/session/storage.js";

const HUB_ORIGIN = "https://hub.example";

function createFakeStorage() {
    const map = new Map();

    return {
        getItem: (key) => (map.has(key) ? map.get(key) : null),
        setItem: (key, value) => map.set(key, String(value)),
        removeItem: (key) => map.delete(key),
    };
}

function createFakeWindow({ origin = "https://news.example", embedded = true } = {}) {
    const listeners = new Map();
    const sent = [];

    const parent = {
        postMessage(message, targetOrigin) {
            sent.push({ message, targetOrigin });
        },
    };

    const win = {
        self: null,
        top: null,
        parent,
        document: { referrer: "" },
        location: { origin },
        addEventListener(type, handler) {
            if (!listeners.has(type)) {
                listeners.set(type, new Set());
            }

            listeners.get(type).add(handler);
        },
        removeEventListener(type, handler) {
            listeners.get(type)?.delete(handler);
        },
        dispatchMessage(event) {
            for (const handler of listeners.get("message") ?? []) {
                handler(event);
            }
        },
    };

    win.self = win;
    win.top = embedded ? {} : win;

    return { win, sent };
}

function authEvent(win, origin = HUB_ORIGIN, payload = {
    username: "Admin",
    role: "admin",
    accessToken: "token-1",
}) {
    return {
        origin,
        source: win.parent,
        data: { type: MESSAGE_AUTH, payload },
    };
}

test("normaliseOrigins trims, drops blanks and strips trailing slashes", () => {
    assert.deepEqual(
        normaliseOrigins("https://a.example/, https://b.example ,, "),
        ["https://a.example", "https://b.example"],
    );
});

test("isAllowedOrigin compares origins without trailing slashes", () => {
    assert.equal(
        isAllowedOrigin("https://a.example/", ["https://a.example"]),
        true,
    );

    assert.equal(
        isAllowedOrigin("https://evil.example", ["https://a.example"]),
        false,
    );

    assert.equal(isAllowedOrigin("", ["https://a.example"]), false);
});

test("a session from an allow-listed parent is accepted and stored", () => {
    const { win } = createFakeWindow();
    const storage = createFakeStorage();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage,
    });

    bridge.install();

    win.dispatchMessage(authEvent(win));

    assert.deepEqual(readSession(storage), {
        username: "Admin",
        role: "admin",
        accessToken: "token-1",
    });
});

test("a session from an origin that is not allow-listed is ignored", () => {
    const { win } = createFakeWindow();
    const storage = createFakeStorage();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage,
    });

    bridge.install();

    win.dispatchMessage(authEvent(win, "https://evil.example"));

    assert.equal(readSession(storage), null);
});

test("a session from a window that is not the parent is ignored", () => {
    const { win } = createFakeWindow();
    const storage = createFakeStorage();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage,
    });

    bridge.install();

    win.dispatchMessage({
        ...authEvent(win),
        source: {},
    });

    assert.equal(readSession(storage), null);
});

test("a malformed payload is ignored", () => {
    const { win } = createFakeWindow();
    const storage = createFakeStorage();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage,
    });

    bridge.install();

    win.dispatchMessage(authEvent(win, HUB_ORIGIN, { username: "Admin" }));
    win.dispatchMessage(authEvent(win, HUB_ORIGIN, null));
    win.dispatchMessage(authEvent(win, HUB_ORIGIN, "token"));

    assert.equal(readSession(storage), null);
});

test("a logout message clears the stored session", () => {
    const { win } = createFakeWindow();
    const storage = createFakeStorage();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage,
    });

    bridge.install();

    win.dispatchMessage(authEvent(win));

    assert.notEqual(readSession(storage), null);

    win.dispatchMessage({
        origin: HUB_ORIGIN,
        source: win.parent,
        data: { type: MESSAGE_LOGOUT },
    });

    assert.equal(readSession(storage), null);
});

test("requestSession resolves once the parent answers", async () => {
    const { win } = createFakeWindow();
    const storage = createFakeStorage();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage,
    });

    const pending = bridge.requestSession();

    win.dispatchMessage(authEvent(win));

    const session = await pending;

    assert.equal(session.accessToken, "token-1");
});

test("requestSession resolves with null after the handshake timeout", async () => {
    const { win } = createFakeWindow();
    const storage = createFakeStorage();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage,
        timeoutMs: 30,
    });

    const session = await bridge.requestSession();

    assert.equal(session, null);
});

test("ready is posted to an explicit origin, never to a wildcard", () => {
    const { win, sent } = createFakeWindow();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage: createFakeStorage(),
    });

    bridge.install();

    assert.ok(sent.length > 0);
    assert.equal(sent[0].message.type, MESSAGE_READY);

    for (const entry of sent) {
        assert.notEqual(entry.targetOrigin, "*");
        assert.equal(entry.targetOrigin, HUB_ORIGIN);
    }
});

test("the allow-listed referrer origin is preferred when posting", () => {
    const { win, sent } = createFakeWindow();

    win.document.referrer = "https://hub.example/landing.html?x=1";

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage: createFakeStorage(),
    });

    bridge.install();

    assert.equal(sent[0].targetOrigin, HUB_ORIGIN);
});

test("a same-origin parent is trusted without an explicit entry", () => {
    const { win } = createFakeWindow({ origin: "https://hub.example" });
    const storage = createFakeStorage();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [],
        win,
        storage,
    });

    bridge.install();

    win.dispatchMessage(authEvent(win, "https://hub.example"));

    assert.notEqual(readSession(storage), null);
});

test("a bridge that is not embedded ignores everything", async () => {
    const { win } = createFakeWindow({ embedded: false });
    const storage = createFakeStorage();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage,
    });

    bridge.install();

    win.dispatchMessage(authEvent(win));

    assert.equal(readSession(storage), null);
    assert.equal(await bridge.requestSession(), null);
});

test("a session that was just revoked is not accepted again", () => {
    const { win, sent } = createFakeWindow();
    const storage = createFakeStorage();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage,
    });

    bridge.install();

    // The session is established first.
    win.dispatchMessage(authEvent(win));

    assert.notEqual(readSession(storage), null);

    // The host ends the session.
    win.dispatchMessage({
        origin: HUB_ORIGIN,
        source: win.parent,
        data: { type: MESSAGE_LOGOUT },
    });

    assert.equal(readSession(storage), null);

    // A handshake that was already in flight arrives afterwards and
    // carries the same token. It must not revive the session.
    win.dispatchMessage(authEvent(win));

    assert.equal(readSession(storage), null);

    // The host confirms that the sign-out was completed.
    const ack = sent.find(
        (entry) => entry.message.type === MESSAGE_LOGOUT_ACK,
    );

    assert.ok(ack, "the bridge acknowledges the sign-out");
    assert.notEqual(ack.targetOrigin, "*");
});

test("a different session is accepted after a sign-out", () => {
    const { win } = createFakeWindow();
    const storage = createFakeStorage();

    const bridge = createParentSessionBridge({
        allowedParentOrigins: [HUB_ORIGIN],
        win,
        storage,
    });

    bridge.install();

    win.dispatchMessage({
        origin: HUB_ORIGIN,
        source: win.parent,
        data: { type: MESSAGE_LOGOUT },
    });

    win.dispatchMessage(
        authEvent(win, HUB_ORIGIN, {
            username: "Viewer",
            role: "user",
            accessToken: "token-2",
        }),
    );

    assert.deepEqual(readSession(storage), {
        username: "Viewer",
        role: "user",
        accessToken: "token-2",
    });
});

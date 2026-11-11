import assert from "node:assert/strict";
import { test } from "node:test";

import {
    MESSAGE_AUTH,
    MESSAGE_LOGOUT,
    MESSAGE_LOGOUT_ACK,
    MESSAGE_NAVIGATE,
    MESSAGE_READY,
    MESSAGE_ROUTE,
    createFrameBridge,
    isAllowedOrigin,
    normaliseOrigins,
} from "../src/session/frameBridge.js";

const NEWS_ORIGIN = "http://localhost:5173";

function createFakeWindow({ origin = "http://localhost:5174" } = {}) {
    const listeners = new Map();

    const win = {
        location: { origin, href: `${origin}/` },
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

    return { win };
}

function createFakeFrame(src = `${NEWS_ORIGIN}/`) {
    const sent = [];

    const frameWindow = {
        postMessage(message, targetOrigin) {
            sent.push({ message, targetOrigin });
        },
    };

    return {
        element: { src, contentWindow: frameWindow },
        sent,
        frameWindow,
    };
}

const SESSION = {
    username: "admin",
    roleNews: "admin",
    accessToken: "token-1",
};

test("normaliseOrigins trims, drops blanks and strips trailing slashes", () => {
    assert.deepEqual(
        normaliseOrigins("http://a.example/, http://b.example ,, "),
        ["http://a.example", "http://b.example"],
    );
});

test("isAllowedOrigin compares origins without trailing slashes", () => {
    assert.equal(
        isAllowedOrigin("http://a.example/", ["http://a.example"]),
        true,
    );

    assert.equal(
        isAllowedOrigin("http://evil.example", ["http://a.example"]),
        false,
    );
});

test("the session is posted to the exact origin of the frame", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.setSession(SESSION);

    bridge.setFrameElement(frame.element);
    bridge.sendSession();

    assert.equal(frame.sent.length, 1);
    assert.equal(frame.sent[0].targetOrigin, NEWS_ORIGIN);
    assert.equal(frame.sent[0].message.type, MESSAGE_AUTH);
    assert.equal(frame.sent[0].message.payload.accessToken, "token-1");
});

test("nothing is posted to a frame from an origin that is not allow-listed", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame("http://evil.example/");

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.setSession(SESSION);

    bridge.setFrameElement(frame.element);

    assert.equal(bridge.sendSession(), false);
    assert.equal(frame.sent.length, 0);
});

test("a ready message from the frame is answered with the session", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.setSession(SESSION);

    bridge.setFrameElement(frame.element);
    bridge.install();

    win.dispatchMessage({
        origin: NEWS_ORIGIN,
        source: frame.frameWindow,
        data: { type: MESSAGE_READY },
    });

    assert.equal(frame.sent.length, 1);
    assert.equal(frame.sent[0].message.type, MESSAGE_AUTH);
});

test("a ready message from a different window is ignored", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.setSession(SESSION);

    bridge.setFrameElement(frame.element);
    bridge.install();

    win.dispatchMessage({
        origin: NEWS_ORIGIN,
        source: {},
        data: { type: MESSAGE_READY },
    });

    assert.equal(frame.sent.length, 0);
});

test("a ready message from a disallowed origin is ignored", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.setSession(SESSION);

    bridge.setFrameElement(frame.element);
    bridge.install();

    win.dispatchMessage({
        origin: "http://evil.example",
        source: frame.frameWindow,
        data: { type: MESSAGE_READY },
    });

    assert.equal(frame.sent.length, 0);
});

test("a logout message from the frame is reported to the host", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    let reported = false;

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
        getSession: () => SESSION,
        onChildLogout: () => {
            reported = true;
        },
    });

    bridge.setFrameElement(frame.element);
    bridge.install();

    win.dispatchMessage({
        origin: NEWS_ORIGIN,
        source: frame.frameWindow,
        data: { type: MESSAGE_LOGOUT },
    });

    assert.equal(reported, true);
});

test("a logout message from a disallowed origin is ignored", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    let reported = false;

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
        getSession: () => SESSION,
        onChildLogout: () => {
            reported = true;
        },
    });

    bridge.setFrameElement(frame.element);
    bridge.install();

    win.dispatchMessage({
        origin: "http://evil.example",
        source: frame.frameWindow,
        data: { type: MESSAGE_LOGOUT },
    });

    assert.equal(reported, false);
});

test("nothing is posted while no frame is mounted", () => {
    const { win } = createFakeWindow();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.setSession(SESSION);

    assert.equal(bridge.sendSession(), false);
    assert.equal(bridge.notifyChildLogout(), false);
});

test("the session handed to the frame follows the one that was set", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.setFrameElement(frame.element);

    bridge.setSession(SESSION);
    bridge.sendSession();

    bridge.setSession({
        username: "viewer",
        roleNews: "user",
        accessToken: "token-2",
    });
    bridge.sendSession();

    assert.equal(frame.sent.length, 2);
    assert.equal(frame.sent[0].message.payload.username, "admin");
    assert.equal(frame.sent[1].message.payload.username, "viewer");
    assert.equal(frame.sent[1].message.payload.accessToken, "token-2");
});

test("no session is sent once the host has asked the frame to sign out", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.setFrameElement(frame.element);
    bridge.setSession(SESSION);

    bridge.notifyChildLogout();

    const sentBefore = frame.sent.length;

    // A handshake that arrives while the sign-out is in progress must
    // not hand the session over again.
    win.dispatchMessage({
        origin: NEWS_ORIGIN,
        source: frame.frameWindow,
        data: { type: MESSAGE_READY },
    });

    assert.equal(
        frame.sent.length,
        sentBefore,
        "nothing is sent while the sign-out is in progress",
    );
});

test("a new session is handed over again after a sign-out", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.setFrameElement(frame.element);
    bridge.setSession(SESSION);
    bridge.notifyChildLogout();

    bridge.setSession({
        username: "viewer",
        roleNews: "user",
        accessToken: "token-2",
    });

    assert.equal(bridge.sendSession(), true);

    const auth = frame.sent.find(
        (entry) => entry.message.type === MESSAGE_AUTH,
    );

    assert.equal(auth.message.payload.accessToken, "token-2");
});

test("the sign-out is repeated until the frame confirms it", async () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.setFrameElement(frame.element);
    bridge.setSession(SESSION);
    bridge.install();

    bridge.notifyChildLogout();

    assert.equal(frame.sent.length, 1);

    // The frame is still starting up and has not confirmed yet, so the
    // request is repeated.
    await new Promise((resolve) => setTimeout(resolve, 200));

    const logouts = frame.sent.filter(
        (entry) => entry.message.type === MESSAGE_LOGOUT,
    );

    assert.ok(logouts.length > 1, "the sign-out is repeated");

    // The frame confirms, and the repetition stops.
    win.dispatchMessage({
        origin: NEWS_ORIGIN,
        source: frame.frameWindow,
        data: { type: MESSAGE_LOGOUT_ACK },
    });

    const confirmed = frame.sent.length;

    await new Promise((resolve) => setTimeout(resolve, 200));

    assert.equal(frame.sent.length, confirmed);

    bridge.uninstall();
});

test("a service that takes a ticket is given the ticket, not the token", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.install();
    bridge.setFrameElement(frame.element);

    bridge.setAuthPayload({
        username: "analyst",
        roleBench: "maker",
        ticket: "ticket-1",
    });

    bridge.sendSession();

    assert.equal(frame.sent.length, 1);
    assert.equal(frame.sent[0].message.type, MESSAGE_AUTH);
    assert.deepEqual(frame.sent[0].message.payload, {
        username: "analyst",
        roleBench: "maker",
        ticket: "ticket-1",
    });
});

test("nothing is sent while a service is still waiting for its ticket", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.install();
    bridge.setFrameElement(frame.element);

    bridge.setAuthPayload(null);

    assert.equal(bridge.sendSession(), false);
    assert.equal(frame.sent.length, 0);
});

test("the session is not sent once a payload was set to nothing", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.install();
    bridge.setFrameElement(frame.element);

    bridge.setSession(SESSION);
    bridge.setAuthPayload(null);

    assert.equal(bridge.sendSession(), false);
    assert.equal(frame.sent.length, 0);
});

test("the hub can ask the embedded application for another screen", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.install();
    bridge.setFrameElement(frame.element);

    assert.equal(bridge.navigate("/trends"), true);
    assert.equal(frame.sent[0].message.type, MESSAGE_NAVIGATE);
    assert.deepEqual(frame.sent[0].message.payload, { path: "/trends" });
});

test("the rail follows the screen the embedded application moved to", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const seen = [];

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
        onChildRoute: (payload) => seen.push(payload.path),
    });

    bridge.install();
    bridge.setFrameElement(frame.element);

    win.dispatchMessage({
        source: frame.frameWindow,
        origin: NEWS_ORIGIN,
        data: { type: MESSAGE_ROUTE, payload: { path: "/compare" } },
    });

    assert.deepEqual(seen, ["/compare"]);
});

test("the route handler can be replaced", () => {
    const { win } = createFakeWindow();
    const frame = createFakeFrame();

    const seen = [];

    const bridge = createFrameBridge({
        allowedChildOrigins: [NEWS_ORIGIN],
        win,
    });

    bridge.install();
    bridge.setFrameElement(frame.element);

    bridge.setRouteHandler((payload) => seen.push(payload.path));

    win.dispatchMessage({
        source: frame.frameWindow,
        origin: NEWS_ORIGIN,
        data: { type: MESSAGE_ROUTE, payload: { path: "/reports" } },
    });

    assert.deepEqual(seen, ["/reports"]);
});

/**
 * Parent session bridge.
 *
 * The landing page (the hub) embeds this application inside an iframe and
 * owns authentication: the user signs in on the hub, not here.
 *
 * The two applications are normally served from different origins, so the
 * access token cannot simply be read from a shared localStorage. It is
 * handed over explicitly over postMessage instead:
 *
 *   child -> parent : { type: "hubint:ready" }
 *   parent -> child : { type: "hubint:auth", payload: { username, roleNews, accessToken } }
 *   parent -> child : { type: "hubint:logout" }
 *   child -> parent : { type: "hubint:logout" }
 *
 * Every inbound message is checked against an origin allowlist and against
 * the expected source window, so a third-party page cannot inject a
 * session into this application. Outbound messages are always addressed to
 * a specific origin; "*" is never used.
 *
 * This module is intentionally free of any framework or bundler specific
 * API so that it can be unit tested under plain Node.
 */

import {
    clearSession,
    normaliseSession,
    readSession,
    writeSession,
} from "./storage.js";

export const MESSAGE_AUTH = "hubint:auth";

export const MESSAGE_LOGOUT = "hubint:logout";

export const MESSAGE_LOGOUT_ACK = "hubint:logout-ack";

export const MESSAGE_READY = "hubint:ready";

export const DEFAULT_HANDSHAKE_TIMEOUT_MS = 2500;

function stripTrailingSlash(value) {
    return typeof value === "string" ? value.replace(/\/+$/, "") : value;
}

/**
 * Turn a comma separated list (or an array) of origins into a clean
 * allowlist.
 */
export function normaliseOrigins(origins) {
    const list = Array.isArray(origins)
        ? origins
        : String(origins ?? "").split(",");

    return list
        .map((origin) => stripTrailingSlash(String(origin ?? "").trim()))
        .filter(Boolean);
}

export function isAllowedOrigin(origin, allowedOrigins) {
    if (!origin) {
        return false;
    }

    const candidate = stripTrailingSlash(origin);

    return allowedOrigins.some(
        (allowed) => stripTrailingSlash(allowed) === candidate,
    );
}

function readOwnOrigin(win) {
    try {
        return win?.location?.origin ?? null;
    } catch {
        return null;
    }
}

/**
 * Resolve the origin to post messages to.
 *
 * The referrer is preferred because it identifies the document that
 * actually embedded us. It is only used when it is allow-listed, so a
 * hostile referrer cannot be used to redirect the token.
 */
function resolveParentOrigin(win, allowedOrigins) {
    try {
        const referrer = win?.document?.referrer;

        if (referrer) {
            const referrerOrigin = new URL(referrer).origin;

            if (isAllowedOrigin(referrerOrigin, allowedOrigins)) {
                return referrerOrigin;
            }
        }
    } catch {
        // Malformed or unavailable referrer: fall through.
    }

    if (allowedOrigins.length > 0) {
        return allowedOrigins[0];
    }

    return readOwnOrigin(win);
}

export function createParentSessionBridge(options = {}) {
    const {
        allowedParentOrigins = [],
        win = typeof window !== "undefined" ? window : undefined,
        storage = win?.localStorage,
        timeoutMs = DEFAULT_HANDSHAKE_TIMEOUT_MS,
        onSessionChange = () => {},
    } = options;

    const configuredOrigins = normaliseOrigins(allowedParentOrigins);

    const ownOrigin = readOwnOrigin(win);

    // A same-origin parent is inherently trustworthy: it already shares
    // this origin's storage and script context.
    const allowedOrigins = ownOrigin
        ? Array.from(
              new Set([...configuredOrigins, stripTrailingSlash(ownOrigin)]),
          )
        : configuredOrigins;

    let installed = false;

    let pending = null;

    // The access token of a session that has just been ended. A message
    // that carries it is a handshake that was still in flight, and must
    // not revive the session that was just revoked.
    let revokedToken = null;

    function isEmbedded() {
        if (!win) {
            return false;
        }

        try {
            return win.self !== win.top;
        } catch {
            return true;
        }
    }

    function isTrustedEvent(event) {
        if (!event || !isEmbedded()) {
            return false;
        }

        if (event.source !== win.parent) {
            return false;
        }

        return isAllowedOrigin(event.origin, allowedOrigins);
    }

    function settlePending(session) {
        if (!pending) {
            return;
        }

        const { resolve, timer } = pending;

        pending = null;

        clearTimeout(timer);

        resolve(session);
    }

    function handleMessage(event) {
        if (!isTrustedEvent(event)) {
            return;
        }

        const data = event.data;

        if (!data || typeof data !== "object") {
            return;
        }

        if (data.type === MESSAGE_AUTH) {
            const session = normaliseSession(data.payload);

            if (!session) {
                return;
            }

            if (session.accessToken === revokedToken) {
                // This is the session that was just ended, arriving late.
                return;
            }

            revokedToken = null;

            writeSession(session, storage);

            settlePending(session);

            onSessionChange({ status: "authenticated", session });

            return;
        }

        if (data.type === MESSAGE_LOGOUT) {
            const current = readSession(storage);

            revokedToken = current?.accessToken ?? null;

            clearSession(storage);

            settlePending(null);

            onSessionChange({ status: "anonymous", session: null });

            // Confirm that the session has been cleared. The parent
            // removes the frame once it receives this, and a message
            // that is not acknowledged would be lost with the frame.
            postToParent({ type: MESSAGE_LOGOUT_ACK });
        }
    }

    function postToParent(message) {
        if (!isEmbedded()) {
            return false;
        }

        const target = resolveParentOrigin(win, allowedOrigins);

        if (!target) {
            return false;
        }

        try {
            win.parent.postMessage(message, target);
            return true;
        } catch {
            return false;
        }
    }

    function install() {
        if (installed || !win) {
            return;
        }

        installed = true;

        win.addEventListener("message", handleMessage);

        // Announce readiness so an already-loaded parent can push a
        // session without waiting for our request.
        postToParent({ type: MESSAGE_READY });
    }

    function uninstall() {
        if (!installed || !win) {
            return;
        }

        installed = false;

        win.removeEventListener("message", handleMessage);
    }

    /**
     * Ask the parent for a session.
     *
     * Resolves with the session once the parent answers, or with null
     * after the handshake timeout. It never rejects.
     */
    function requestSession() {
        if (!isEmbedded()) {
            return Promise.resolve(null);
        }

        install();

        return new Promise((resolve) => {
            const timer = setTimeout(() => settlePending(null), timeoutMs);

            pending = { resolve, timer };

            postToParent({ type: MESSAGE_READY });
        });
    }

    return {
        allowedOrigins,
        isEmbedded,
        install,
        uninstall,
        postToParent,
        requestSession,
        notifyParentLogout() {
            return postToParent({ type: MESSAGE_LOGOUT });
        },
    };
}

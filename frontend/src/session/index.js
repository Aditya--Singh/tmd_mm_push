/**
 * Application level session wiring.
 *
 * Creates the single parent-session bridge used by the app and exposes
 * the helpers the React layer needs: resolving the session on start-up
 * and reacting to a session that the landing page changes underneath us.
 */

import { envList } from "../config/env.js";
import { createParentSessionBridge } from "./parentSession.js";
import { readHubSession, readSession, writeSession } from "./storage.js";

const listeners = new Set();

let bridge = null;

/**
 * Origins the landing page may be served from when it is not configured
 * explicitly. These are the development and shared-hosting addresses of
 * the hub.
 */
const DEFAULT_PARENT_ORIGINS = [
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://newsintel.pnbbank.in:5174",
];

function notify(change) {
    for (const listener of listeners) {
        listener(change);
    }
}

export function getBridge() {
    if (!bridge) {
        bridge = createParentSessionBridge({
            allowedParentOrigins: envList(
                "VITE_ALLOWED_PARENT_ORIGINS",
                DEFAULT_PARENT_ORIGINS,
            ),
            onSessionChange: notify,
        });
    }

    return bridge;
}

export function onSessionChange(listener) {
    listeners.add(listener);

    return () => listeners.delete(listener);
}

/**
 * True when this application is rendered inside another document.
 *
 * The landing page appends `embedded=1` to the frame URL, and the
 * `window.self !== window.top` check covers frames that were embedded
 * without that hint.
 */
export function isEmbeddedContext() {
    try {
        if (new URLSearchParams(window.location.search).get("embedded") === "1") {
            return true;
        }

        return window.self !== window.top;
    } catch {
        return false;
    }
}

/**
 * Resolve the session to start the application with.
 *
 * When embedded, the landing page is the authority on who is signed in:
 *   1. a hub session in shared storage (same-origin deployment),
 *   2. an explicit handshake with the parent frame,
 *   3. a session left over in this origin's own storage.
 *
 * When opened directly, only the local session applies.
 */
export async function resolveInitialSession() {
    const storage = window.localStorage;

    const current = getBridge();

    if (!current.isEmbedded()) {
        return readSession(storage);
    }

    const hubSession = readHubSession(storage);

    if (hubSession) {
        writeSession(hubSession, storage);

        return hubSession;
    }

    const parentSession = await current.requestSession();

    if (parentSession) {
        return parentSession;
    }

    return readSession(storage);
}

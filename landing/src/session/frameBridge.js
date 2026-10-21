/**
 * Frame session bridge.
 *
 * The landing page embeds the news application in a frame and owns
 * authentication. Because the two are usually served from different
 * origins, the access token is handed to the frame explicitly:
 *
 *   child -> parent : { type: "newsint:ready" }
 *   parent -> child : { type: "newsint:auth", payload: { username, role, accessToken } }
 *   parent -> child : { type: "newsint:logout" }
 *   child -> parent : { type: "newsint:logout" }
 *
 * Messages are only ever sent to the exact origin the frame was loaded
 * from, and messages are only accepted from the frame that is currently
 * mounted and from an allow-listed origin.
 *
 * This module has no framework or bundler specific API so that it can be
 * unit tested under plain Node.
 */

export const MESSAGE_AUTH = "newsint:auth";

export const MESSAGE_LOGOUT = "newsint:logout";

export const MESSAGE_LOGOUT_ACK = "newsint:logout-ack";

export const MESSAGE_READY = "newsint:ready";

/**
 * A frame that is still starting up has not attached its message listener
 * yet, and would not receive a logout request. The request is therefore
 * repeated until the frame confirms that it has signed out.
 */
const LOGOUT_RETRY_INTERVAL_MS = 150;

const LOGOUT_RETRY_LIMIT = 12;

function stripTrailingSlash(value) {
    return typeof value === "string" ? value.replace(/\/+$/, "") : value;
}

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

export function createFrameBridge(options = {}) {
    const {
        allowedChildOrigins = [],
        win = typeof window !== "undefined" ? window : undefined,
        onChildLogout = () => {},
        onChildLogoutAck = () => {},
    } = options;

    const configuredOrigins = normaliseOrigins(allowedChildOrigins);

    let ownOrigin;

    try {
        ownOrigin = win?.location?.origin ?? null;
    } catch {
        ownOrigin = null;
    }

    // A frame served from this origin shares our storage and script
    // context, so it needs no separate entry in the allowlist.
    const allowedOrigins = ownOrigin
        ? Array.from(
              new Set([...configuredOrigins, stripTrailingSlash(ownOrigin)]),
          )
        : configuredOrigins;

    let frameElement = null;

    let installed = false;

    let currentSession = null;

    // Set once the host has asked the frame to sign out. The session is
    // not handed over again while this is set, so that a handshake that
    // is still in flight cannot revive a session that is being ended.
    let signedOut = false;

    let logoutRetries = null;

    let logoutRetryCount = 0;

    function frameOrigin() {
        if (!frameElement) {
            return null;
        }

        try {
            return new URL(frameElement.src, win.location.href).origin;
        } catch {
            return null;
        }
    }

    function isTrustedEvent(event) {
        if (!event || !frameElement) {
            return false;
        }

        if (event.source !== frameElement.contentWindow) {
            return false;
        }

        return isAllowedOrigin(event.origin, allowedOrigins);
    }

    function handleMessage(event) {
        if (!isTrustedEvent(event)) {
            return;
        }

        const data = event.data;

        if (!data || typeof data !== "object") {
            return;
        }

        if (data.type === MESSAGE_READY) {
            // The frame is asking for a session. Answer immediately.
            sendSession();
            return;
        }

        if (data.type === MESSAGE_LOGOUT) {
            onChildLogout();
            return;
        }

        if (data.type === MESSAGE_LOGOUT_ACK) {
            stopLogoutRetries();

            onChildLogoutAck();
        }
    }

    function stopLogoutRetries() {
        if (logoutRetries) {
            clearInterval(logoutRetries);
            logoutRetries = null;
        }

        logoutRetryCount = 0;
    }

    function startLogoutRetries() {
        if (logoutRetries) {
            return;
        }

        logoutRetries = setInterval(() => {
            logoutRetryCount += 1;

            if (logoutRetryCount > LOGOUT_RETRY_LIMIT || !frameElement) {
                stopLogoutRetries();
                return;
            }

            post({ type: MESSAGE_LOGOUT });
        }, LOGOUT_RETRY_INTERVAL_MS);
    }

    function install() {
        if (installed || !win) {
            return;
        }

        installed = true;

        win.addEventListener("message", handleMessage);
    }

    function uninstall() {
        stopLogoutRetries();

        if (!installed || !win) {
            return;
        }

        installed = false;

        win.removeEventListener("message", handleMessage);
    }

    function post(message) {
        if (!frameElement) {
            return false;
        }

        const target = frameOrigin();

        if (!target || !isAllowedOrigin(target, allowedOrigins)) {
            return false;
        }

        try {
            frameElement.contentWindow.postMessage(message, target);
            return true;
        } catch {
            return false;
        }
    }

    function sendSession() {
        const session = currentSession;

        if (!session || signedOut) {
            return false;
        }

        return post({
            type: MESSAGE_AUTH,
            payload: {
                username: session.username,
                role: session.role,
                accessToken: session.accessToken,
            },
        });
    }

    return {
        allowedOrigins,
        install,
        uninstall,
        setFrameElement(element) {
            frameElement = element;

            if (!element) {
                stopLogoutRetries();
            }
        },
        setSession(session) {
            currentSession = session;

            if (session) {
                // A new session replaces a session that was ended.
                signedOut = false;

                stopLogoutRetries();
            }
        },
        post,
        sendSession,
        notifyChildLogout() {
            signedOut = true;

            startLogoutRetries();

            return post({ type: MESSAGE_LOGOUT });
        },
    };
}

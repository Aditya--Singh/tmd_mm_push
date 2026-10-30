/**
 * Frame session bridge.
 *
 * The landing page embeds an application in a frame and owns
 * authentication. Because the two are usually served from different
 * origins, the session is handed to the frame explicitly:
 *
 *   child -> parent : { type: "hubint:ready" }
 *   parent -> child : { type: "hubint:auth", payload: { username, role, accessToken } }
 *   parent -> child : { type: "hubint:logout" }
 *   child -> parent : { type: "hubint:logout" }
 *
 * The payload depends on the service. The news application shares this
 * platform's token and takes { username, role, accessToken }. Peer
 * Benchmarking keeps its own sessions, so it is handed a single-use
 * sign-in ticket instead: { username, role, ticket }.
 *
 * The landing page can also drive the frame:
 *
 *   parent -> child : { type: "hubint:navigate", payload: { path } }
 *
 * Messages are only ever sent to the exact origin the frame was loaded
 * from, and messages are only accepted from the frame that is currently
 * mounted and from an allow-listed origin.
 *
 * This module has no framework or bundler specific API so that it can be
 * unit tested under plain Node.
 */

export const MESSAGE_AUTH = "hubint:auth";

export const MESSAGE_LOGOUT = "hubint:logout";

export const MESSAGE_LOGOUT_ACK = "hubint:logout-ack";

export const MESSAGE_READY = "hubint:ready";

export const MESSAGE_NAVIGATE = "hubint:navigate";

export const MESSAGE_ROUTE = "hubint:route";

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
        onChildRoute = () => {},
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

    // The payload handed to the frame.
    //
    // It is the only thing the frame is ever given, so a service that is
    // still waiting for its sign-in ticket simply holds nothing: null
    // means "nothing to send yet".
    let authPayload = null;

    // Set once the host has asked the frame to sign out. The session is
    // not handed over again while this is set, so that a handshake that
    // is still in flight cannot revive a session that is being ended.
    let signedOut = false;

    let logoutRetries = null;

    let logoutRetryCount = 0;

    // Told which screen the embedded application moved to.
    let routeHandler = onChildRoute;

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
            // The frame is asking for a session. Answer immediately, and
            // to the origin the frame really has, which is known for
            // certain here.
            sendSession(event.origin);
            return;
        }

        if (data.type === MESSAGE_LOGOUT) {
            onChildLogout();
            return;
        }

        if (data.type === MESSAGE_LOGOUT_ACK) {
            stopLogoutRetries();

            onChildLogoutAck();
            return;
        }

        if (data.type === MESSAGE_ROUTE) {
            // The embedded application moved to another screen. The rail
            // follows, so that the two never disagree.
            routeHandler(data.payload ?? {});
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

    /**
     * Send a message to the frame.
     *
     * The origin is taken from the frame's address unless a caller knows
     * better. A frame that has not navigated yet holds an empty document
     * that belongs to this page, so posting to it would go astray; the
     * address of the frame is used instead.
     */
    function post(message, knownOrigin = null) {
        if (!frameElement) {
            return false;
        }

        const target = knownOrigin ?? frameOrigin();

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

    function sendSession(knownOrigin = null) {
        const payload = authPayload;

        if (!payload || signedOut) {
            return false;
        }

        return post(
            {
                type: MESSAGE_AUTH,
                payload,
            },
            knownOrigin,
        );
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
        /**
         * Hand the session of the landing page to the frame. This is what
         * a service that shares this platform's sessions takes.
         */
        setSession(session) {
            if (session) {
                // A new session replaces a session that was ended.
                signedOut = false;

                stopLogoutRetries();

                authPayload = {
                    username: session.username,
                    role: session.role,
                    accessToken: session.accessToken,
                };
            }
        },
        /**
         * Set exactly what is handed to the frame. Pass null when there
         * is nothing to send yet, which is what a service that is still
         * waiting for its sign-in ticket needs.
         */
        setAuthPayload(payload) {
            authPayload = payload;

            if (payload) {
                signedOut = false;

                stopLogoutRetries();
            }
        },
        /**
         * Ask the embedded application to show a different screen.
         */
        navigate(path) {
            if (typeof path !== "string" || !path) {
                return false;
            }

            return post({
                type: MESSAGE_NAVIGATE,
                payload: { path },
            });
        },
        /**
         * Set what happens when the embedded application moves to
         * another screen.
         */
        setRouteHandler(handler) {
            routeHandler = typeof handler === "function" ? handler : () => {};
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

/**
 * Environment access.
 *
 * Vite replaces `import.meta.env` with a static object at build time and
 * provides it at runtime in development. The optional access keeps this
 * module importable from plain Node, where `import.meta.env` is undefined
 * and the unit tests run.
 */

const viteEnv = import.meta.env ?? {};

export const env = viteEnv;

/**
 * The backend the landing page's own server forwards the request to.
 *
 * During development the request for /api is proxied to the backend, so the browser
 * never leaves the origin of the landing page. The address is put here by the build so
 * that a sign-in that cannot go through can say where it was meant to go.
 */
export const apiProxyTarget =
    typeof __API_PROXY_TARGET__ === "undefined" ? "" : __API_PROXY_TARGET__;

/**
 * Read a comma separated environment variable as a trimmed list.
 *
 * A fallback is used when the variable is not set, so that the
 * application works out of the box in development.
 */
export function envList(name, fallback = []) {
    const raw = env[name];

    if (typeof raw !== "string" || !raw.trim()) {
        return fallback;
    }

    return raw
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
}

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

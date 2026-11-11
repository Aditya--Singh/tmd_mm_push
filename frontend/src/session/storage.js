/**
 * Session storage helpers.
 *
 * The access token is kept in localStorage under a fixed key so that the
 * existing axios interceptor in `src/api/client.js` can attach it to every
 * request without further changes.
 *
 * The session holds the role the person holds in this application, which is
 * the `role_news` column of the `users` table. The role they hold in Peer
 * Benchmarking is not carried here: that application keeps its own sessions.
 *
 * Two keys are in play:
 *
 *   bankNewsUser    - the session used by this application.
 *   bankHubSession  - the session owned by the landing page (the hub).
 *
 * The hub key is only ever visible when both applications are served from
 * the same origin, which is the case for a reverse-proxied deployment. In
 * that situation the hub session is the authoritative one, because the hub
 * owns authentication and can invalidate it at any time.
 */

export const SESSION_STORAGE_KEY = "bankNewsUser";

export const HUB_SESSION_STORAGE_KEY = "bankHubSession";

/**
 * Normalise a session payload into the shape the application expects.
 *
 * Accepts both the camelCase form used by the frontend and the snake_case
 * form returned by the API, and rejects anything that is missing a field
 * we cannot work without.
 */
export function normaliseSession(session) {
    if (!session || typeof session !== "object") {
        return null;
    }

    const accessToken = session.accessToken ?? session.access_token;

    const username = session.username;

    const roleNews = session.roleNews ?? session.role_news;

    if (typeof accessToken !== "string" || !accessToken) {
        return null;
    }

    if (typeof username !== "string" || !username) {
        return null;
    }

    if (typeof roleNews !== "string" || !roleNews) {
        return null;
    }

    return { username, roleNews, accessToken };
}

function safeGet(storage, key) {
    try {
        return storage.getItem(key);
    } catch {
        // Storage can be unavailable (private mode, disabled cookies).
        return null;
    }
}

function safeSet(storage, key, value) {
    try {
        storage.setItem(key, value);
        return true;
    } catch {
        return false;
    }
}

function safeRemove(storage, key) {
    try {
        storage.removeItem(key);
    } catch {
        // Ignore: nothing we can do if storage is unavailable.
    }
}

export function parseSession(raw) {
    if (!raw) {
        return null;
    }

    try {
        return normaliseSession(JSON.parse(raw));
    } catch {
        return null;
    }
}

export function readSession(storage) {
    return parseSession(safeGet(storage, SESSION_STORAGE_KEY));
}

export function writeSession(session, storage) {
    const normalised = normaliseSession(session);

    if (!normalised) {
        return null;
    }

    safeSet(storage, SESSION_STORAGE_KEY, JSON.stringify(normalised));

    return normalised;
}

export function clearSession(storage) {
    safeRemove(storage, SESSION_STORAGE_KEY);
}

export function readHubSession(storage) {
    return parseSession(safeGet(storage, HUB_SESSION_STORAGE_KEY));
}

/**
 * Landing page session storage.
 *
 * The landing page owns authentication. The access token is kept under
 * `bankHubSession` so that it is distinct from the news application's own
 * `bankNewsUser` key while still being readable by it when both are served
 * from the same origin.
 */

export const HUB_SESSION_STORAGE_KEY = "bankHubSession";

export function normaliseSession(session) {
    if (!session || typeof session !== "object") {
        return null;
    }

    const accessToken = session.accessToken ?? session.access_token;

    const username = session.username;

    const role = session.role;

    if (typeof accessToken !== "string" || !accessToken) {
        return null;
    }

    if (typeof username !== "string" || !username) {
        return null;
    }

    if (typeof role !== "string" || !role) {
        return null;
    }

    return { username, role, accessToken };
}

function safeGet(storage, key) {
    try {
        return storage.getItem(key);
    } catch {
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
        // Nothing can be done when storage is unavailable.
    }
}

export function readHubSession(storage) {
    const raw = safeGet(storage, HUB_SESSION_STORAGE_KEY);

    if (!raw) {
        return null;
    }

    try {
        return normaliseSession(JSON.parse(raw));
    } catch {
        return null;
    }
}

export function writeHubSession(session, storage) {
    const normalised = normaliseSession(session);

    if (!normalised) {
        return null;
    }

    safeSet(storage, HUB_SESSION_STORAGE_KEY, JSON.stringify(normalised));

    return normalised;
}

export function clearHubSession(storage) {
    safeRemove(storage, HUB_SESSION_STORAGE_KEY);
}

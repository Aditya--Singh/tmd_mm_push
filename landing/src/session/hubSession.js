/**
 * Landing page session storage.
 *
 * The landing page owns authentication. The access token is kept under
 * `bankHubSession` so that it is distinct from the news application's own
 * `bankNewsUser` key while still being readable by it when both are served
 * from the same origin.
 *
 * A person holds one role in each application, so the session carries both:
 * `roleNews` for the News Feed and `roleBench` for Peer Benchmarking.
 */

export const HUB_SESSION_STORAGE_KEY = "bankHubSession";

export function normaliseSession(session) {
    if (!session || typeof session !== "object") {
        return null;
    }

    const accessToken = session.accessToken ?? session.access_token;

    const username = session.username;

    const roleNews = session.roleNews ?? session.role_news;

    const roleBench = session.roleBench ?? session.role_bench;

    // The name of each role, for the interface. They are optional, because
    // the roles themselves are what matters.
    const roleNewsLabel = session.roleNewsLabel ?? session.role_news_label ?? null;

    const roleBenchLabel =
        session.roleBenchLabel ?? session.role_bench_label ?? null;

    if (typeof accessToken !== "string" || !accessToken) {
        return null;
    }

    if (typeof username !== "string" || !username) {
        return null;
    }

    if (typeof roleNews !== "string" || !roleNews) {
        return null;
    }

    if (typeof roleBench !== "string" || !roleBench) {
        return null;
    }

    return {
        username,
        accessToken,
        roleNews,
        roleBench,
        roleNewsLabel,
        roleBenchLabel,
    };
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

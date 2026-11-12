/**
 * What to say when a sign-in does not go through.
 *
 * The landing page used to say the same thing for every failure: "Unable to connect to
 * the authentication service". That is not enough to act on. The backend may not be
 * running, the address may be wrong, the browser may have blocked the request, or the
 * credentials may simply be wrong, and each of those needs a different answer.
 */

/**
 * The address the request is sent to.
 *
 * An empty base URL means the request goes to the landing page's own server, which
 * forwards it to the backend during development and behind a reverse proxy in production.
 */
export function apiAddress(baseUrl, origin) {
    const base = String(baseUrl ?? "").trim();

    if (base) {
        return base.replace(/\/+$/, "");
    }

    return String(origin ?? "").replace(/\/+$/, "");
}

/**
 * The backend the landing page's own server forwards the request to.
 */
export function proxyTarget(target) {
    const value = String(target ?? "").trim();

    return value ? value.replace(/\/+$/, "") : "";
}

/**
 * Describe a failed sign-in.
 *
 * @param {object} error - the error the request failed with.
 * @param {{baseUrl?: string, origin?: string, proxyTarget?: string}} context -
 *   where the request was sent.
 * @returns {{message: string, detail: string}} - what to show, and what to point at.
 */
export function describeLoginFailure(error, context = {}) {
    const address = apiAddress(context.baseUrl, context.origin);
    const target = proxyTarget(context.proxyTarget);

    const status = error?.response?.status;
    const detail = error?.response?.data?.detail;

    if (status === 401 || status === 403) {
        return {
            message: "Invalid username or password.",
            detail: "",
        };
    }

    // The landing page's own server answered, but it could not reach the backend.
    if (status === 502 || status === 503 || status === 504) {
        return {
            message:
                "The backend is not answering, so the sign-in could not be checked.",
            detail: target
                ? `Start it: cd backend && uv run python -m uvicorn app.main:app --port 8000 (it is expected at ${target}).`
                : "Start it: cd backend && uv run python -m uvicorn app.main:app --port 8000",
        };
    }

    // The request never arrived: the address is wrong, or the browser blocked it.
    if (!status) {
        return {
            message:
                "The browser could not reach the authentication service.",
            detail: [
                address
                    ? `The request was sent to ${address}/api/auth/login.`
                    : "",
                "If the backend is on another address, set VITE_API_BASE_URL in landing/.env.",
                "If the browser blocked the request, add this address to CORS_ORIGINS in backend/.env.",
            ]
                .filter(Boolean)
                .join(" "),
        };
    }

    return {
        message: `The authentication service answered with ${status}.`,
        detail: detail ? String(detail) : "",
    };
}

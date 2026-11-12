/**
 * What to say when a sign-in does not go through.
 *
 * The news application used to say the same thing for every failure: "Unable to connect
 * to the authentication service". The backend may not be running, the address may be
 * wrong, or the credentials may simply be wrong, and each needs a different answer.
 */

/**
 * Describe a failed sign-in.
 *
 * @param {object} error - the error the request failed with.
 * @returns {{message: string, detail: string}} - what to show, and what to point at.
 */
export function describeLoginFailure(error) {
    const status = error?.response?.status;
    const detail = error?.response?.data?.detail;

    if (status === 401 || status === 403) {
        return {
            message: "Invalid username or password.",
            detail: "",
        };
    }

    // The server of the application answered, but it could not reach the backend.
    if (status === 502 || status === 503 || status === 504) {
        return {
            message:
                "The backend is not answering, so the sign-in could not be checked.",
            detail:
                "Start it: cd backend && uv run python -m uvicorn app.main:app --port 8000",
        };
    }

    // The request never arrived: the address is wrong, or the browser blocked it.
    if (!status) {
        return {
            message: "The browser could not reach the authentication service.",
            detail: [
                "If the backend is on another address, set VITE_API_BASE_URL in .env.",
                "If the browser blocked the request, add this address to CORS_ORIGINS in backend/.env.",
            ].join(" "),
        };
    }

    return {
        message: `The authentication service answered with ${status}.`,
        detail: detail ? String(detail) : "",
    };
}

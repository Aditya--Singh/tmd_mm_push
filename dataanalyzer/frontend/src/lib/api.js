// The API of this app. In the development server the API is on the same address, so that
// the browser is never told where it is.

const TOKEN_KEY = "dataanalyzer.token";

export function readToken() {
    try {
        return window.localStorage.getItem(TOKEN_KEY) || "";
    } catch {
        return "";
    }
}

export function writeToken(token) {
    try {
        if (token) {
            window.localStorage.setItem(TOKEN_KEY, token);
        } else {
            window.localStorage.removeItem(TOKEN_KEY);
        }
    } catch {
        // A browser that keeps nothing is handled by the session check below.
    }
}

export class ApiError extends Error {
    constructor(message, status) {
        super(message);
        this.name = "ApiError";
        this.status = status;
    }
}

async function request(path, options = {}) {
    const token = readToken();

    const response = await fetch(path, {
        ...options,
        headers: {
            ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...(options.headers || {}),
        },
    });

    if (!response.ok) {
        let detail = `The request failed (${response.status}).`;

        try {
            const body = await response.json();

            if (body?.detail) {
                detail = String(body.detail);
            }
        } catch {
            // The answer was not JSON; the first message stands.
        }

        throw new ApiError(detail, response.status);
    }

    if (response.status === 204) {
        return null;
    }

    return response.json();
}

export const listDocuments = () => request("/api/documents");

export const getDocument = (id) => request(`/api/documents/${id}`);

export const uploadDocument = (file) => {
    const body = new FormData();
    body.append("file", file);

    return request("/api/documents", { method: "POST", body });
};

export const removeDocument = (id) => request(`/api/documents/${id}`, { method: "DELETE" });

export const makeSummary = (id) => request(`/api/documents/${id}/summary`, { method: "POST" });

export const makeInsights = (id) => request(`/api/documents/${id}/insights`, { method: "POST" });

export const askAbout = (id, question) =>
    request(`/api/documents/${id}/ask`, {
        method: "POST",
        body: JSON.stringify({ question }),
    });

export const exchangeTicket = (ticket) =>
    request("/api/auth/exchange", {
        method: "POST",
        body: JSON.stringify({ ticket }),
    });

export const meta = () => request("/api/meta");

export const plotUrl = (documentId, file) => `/api/plots/${documentId}/${file}`;

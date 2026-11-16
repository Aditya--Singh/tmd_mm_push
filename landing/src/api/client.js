import axios from "axios";

import { env } from "../config/env.js";
import { readHubSession } from "../session/hubSession.js";

// The API base URL is configurable so that the same build can be pointed
// at a local backend, a shared environment, or a reverse-proxied path.
// An empty value keeps the browser on the current origin, which is what
// the development proxy and a reverse proxied deployment expect.
const apiClient = axios.create({
    baseURL: env.VITE_API_BASE_URL || "",
    headers: {
        "Content-Type": "application/json",
    },
});

// The landing page owns the session, so every call carries the token.
apiClient.interceptors.request.use(
    (config) => {
        const session = readHubSession(window.localStorage);

        if (session?.accessToken) {
            config.headers.Authorization = `Bearer ${session.accessToken}`;
        }

        return config;
    },
    (error) => Promise.reject(error),
);

/**
 * A service that has just been started may not answer the first time.
 *
 * One more try a second later saves the person from being told that a
 * service is down when it is only just coming up.
 */
const RETRYABLE = [502, 503, 504];

apiClient.interceptors.response.use(
    (response) => response,
    async (error) => {
        const status = error?.response?.status;
        const alreadyTried = error?.config?.__hubRetried;

        if (!RETRYABLE.includes(status) || alreadyTried) {
            return Promise.reject(error);
        }

        await new Promise((resolve) => setTimeout(resolve, 1000));

        error.config.__hubRetried = true;

        return apiClient(error.config);
    },
);

export default apiClient;

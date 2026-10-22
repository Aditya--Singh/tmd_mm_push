import axios from "axios";

import { env } from "../config/env";
import { readHubSession } from "../session/hubSession";

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

export default apiClient;

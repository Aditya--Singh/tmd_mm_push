import axios from "axios";

import { env } from "../config/env";

// The API base URL is configurable so that the same build can be pointed
// at a local backend, a shared environment, or a reverse-proxied path.
// An empty value keeps the browser on the current origin, which is what
// both the development proxy and a reverse proxied deployment expect.
const apiClient = axios.create({
    baseURL: env.VITE_API_BASE_URL || "",
    headers: {
        "Content-Type": "application/json",
    },
});

apiClient.interceptors.request.use(
    (config) => {
        const user = JSON.parse(
            localStorage.getItem("bankNewsUser") || "null"
        );

        if (user?.accessToken) {
            config.headers.Authorization =
                `Bearer ${user.accessToken}`;
        }

        return config;
    },
    (error) => Promise.reject(error),
);

apiClient.interceptors.response.use(
    (response) => response,
    (error) => {
        if (error.response?.status === 401) {
            localStorage.removeItem("bankNewsUser");

            // Notify the application that the session is no longer valid
            window.dispatchEvent(new Event("auth-expired"));
        }

        return Promise.reject(error);
    },
);

export default apiClient;

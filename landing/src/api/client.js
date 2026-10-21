import axios from "axios";

import { env } from "../config/env";

// The API base URL is configurable so that the same build can be pointed
// at a local backend, a shared environment, or a reverse-proxied path.
// An empty value keeps the browser on the current origin, which is what
// the development proxy on /api expects.
const apiClient = axios.create({
    baseURL: env.VITE_API_BASE_URL || "",
    headers: {
        "Content-Type": "application/json",
    },
});

export default apiClient;

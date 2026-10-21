import apiClient from "./client";

/**
 * Authenticate against the shared backend.
 *
 * The landing page uses the same users table and the same token as the
 * news application, so a session established here is valid for every
 * service hosted in the hub.
 */
export const login = async (username, password) => {
    const response = await apiClient.post("/api/auth/login", {
        username,
        password,
    });

    return response.data;
};

/**
 * Resolve the signed-in user from an existing access token.
 */
export const me = async (accessToken) => {
    const response = await apiClient.get("/api/auth/me", {
        headers: {
            Authorization: `Bearer ${accessToken}`,
        },
    });

    return response.data;
};

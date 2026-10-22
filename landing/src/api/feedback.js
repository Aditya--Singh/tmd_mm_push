import apiClient from "./client";

/**
 * Record feedback about the platform.
 *
 * The backend takes the signed-in user from the access token, so the
 * username and role do not have to be sent.
 */
export const submitFeedback = async ({
    relevance,
    accuracy,
    usefulness,
    clarity,
    timeliness,
    comments,
}) => {
    const response = await apiClient.post("/api/feedback", {
        relevance,
        accuracy,
        usefulness,
        clarity,
        timeliness,
        comments,
    });

    return response.data;
};

import apiClient from "./client";

/**
 * The Data Summarizer keeps its own database, its own sessions and its own audit
 * trail. The landing page does not take that over: it asks the summarizer's server
 * for a single-use sign-in ticket and hands it to the frame, so that the person
 * who signed in here is signed in there too.
 */

/**
 * The navigation of the Data Summarizer, for the hub's own rail.
 */
export const fetchManifest = async () => {
    const response = await apiClient.get("/api/services/summarizer/manifest");

    return response.data;
};

/**
 * Ask for a single-use sign-in ticket for the signed-in person.
 */
export const requestTicket = async () => {
    const response = await apiClient.post("/api/services/summarizer/ticket");

    return response.data;
};

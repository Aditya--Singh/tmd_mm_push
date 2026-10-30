import apiClient from "./client";

/**
 * Peer Benchmarking keeps its own database, its own sessions and its own
 * audit trail. The landing page does not take that over: it asks the
 * benchmarking server for a single-use sign-in ticket and hands it to the
 * frame, so that the person who signed in here is signed in there too.
 */

/**
 * The navigation of Peer Benchmarking, for the hub's own rail.
 */
export const fetchManifest = async () => {
    const response = await apiClient.get("/api/services/benchmarking/manifest");

    return response.data;
};

/**
 * Ask for a single-use sign-in ticket for the signed-in person.
 */
export const requestTicket = async () => {
    const response = await apiClient.post("/api/services/benchmarking/ticket");

    return response.data;
};

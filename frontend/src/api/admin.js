import apiClient from "./client";

/**
 * Fetch the news and run the AI analysis over it.
 *
 * The number of days says how far back the news may reach. The news published before
 * that day is not fetched and not stored.
 */
export async function runNewsIngestion(days = 30) {
    const response = await apiClient.post(
        "/api/admin/news/ingest",
        { days },
    );

    return response.data;
}

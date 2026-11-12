/**
 * The window the news may reach.
 *
 * The number is the number of days back from today. The news published before that day
 * is not fetched and not stored. The window may be as long as 90 days.
 */

export const MAX_DAYS = 90;

export const DEFAULT_DAYS = 30;

export const WINDOWS = [
    { days: 1, label: "Today only" },
    { days: 3, label: "Last 3 days" },
    { days: 7, label: "Last 7 days" },
    { days: 15, label: "Last 15 days" },
    { days: 30, label: "Last 30 days" },
    { days: 45, label: "Last 45 days" },
    { days: 60, label: "Last 60 days" },
    { days: 90, label: "Last 90 days" },
];

/**
 * The day the window starts at, in the reading of the reader.
 */
export function cutoffDate(days, today = new Date()) {
    const date = new Date(today);

    date.setDate(date.getDate() - days);

    return date.toLocaleDateString("en-IN", {
        day: "2-digit",
        month: "short",
        year: "numeric",
    });
}

/**
 * The intelligence services offered by the hub.
 *
 * `status` marks whether a service is implemented:
 *   live   - the service is available and is opened in the workspace.
 *   planned- the service is part of the platform scope but not built yet.
 *
 * `roles` limits a service to specific roles. A service without the field
 * is available to every signed-in user.
 *
 * `session` says how the signed-in person is handed over to the service:
 *   token  - the service shares this platform's token and sessions.
 *   ticket - the service keeps its own sessions, so it is given a
 *            single-use sign-in ticket instead of the token.
 */

import { env } from "./config/env";

export const SERVICE_STATUS = {
    LIVE: "live",
    PLANNED: "planned",
};

export const SESSION_MODE = {
    TOKEN: "token",
    TICKET: "ticket",
};

export const SERVICES = [
    {
        id: "sql",
        name: "SQL Genie",
        icon: "🧠",
        description:
            "Conversational analytics and natural language data exploration",
        status: SERVICE_STATUS.PLANNED,
    },
    {
        id: "summarizer",
        name: "Data Summarizer",
        icon: "📄",
        description: "PDF, PPT and Excel summarization service",
        status: SERVICE_STATUS.PLANNED,
    },
    {
        id: "benchmark",
        name: "Peer Benchmarking",
        icon: "📊",
        description:
            "Competitive analysis and peer performance comparison",
        status: SERVICE_STATUS.LIVE,
        url: env.VITE_BENCHMARKING_APP_URL || "http://localhost:8077/",
        session: SESSION_MODE.TICKET,
    },
    {
        id: "news",
        name: "News Feed",
        icon: "📰",
        description:
            "External business, banking and regulatory intelligence",
        status: SERVICE_STATUS.LIVE,
        url: env.VITE_NEWS_APP_URL || "http://localhost:5173/",
        session: SESSION_MODE.TOKEN,
    },
];

export function servicesForRole(role) {
    return SERVICES.filter(
        (service) => !service.roles || service.roles.includes(role),
    );
}

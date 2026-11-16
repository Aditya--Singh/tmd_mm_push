/**
 * The intelligence services offered by the hub.
 *
 * `status` marks whether a service is implemented:
 *   live   - the service is available and is opened in the workspace.
 *   planned- the service is part of the platform scope but not built yet.
 *
 * `roles` says which role of which application decides who may open a service.
 * The keys are the columns of the `users` table: `news` and `bench`. A service
 * without the field is available to every signed-in user.
 *
 * `session` says how the signed-in person is handed over to the service:
 *   token  - the service shares this platform's token and sessions.
 *   ticket - the service keeps its own sessions, so it is given a
 *            single-use sign-in ticket instead of the token.
 *
 * `ownAccounts` marks a service that keeps its own accounts and decides the roles
 * there itself. Nobody is named by a column of this platform's user table.
 */

import { env } from "./config/env.js";

export const SERVICE_STATUS = {
    LIVE: "live",
    PLANNED: "planned",
};

export const SESSION_MODE = {
    TOKEN: "token",
    TICKET: "ticket",
};

/**
 * The roles each application knows, as they are named in the `users` table.
 */
export const NEWS_ROLES = ["admin", "user"];

export const BENCH_ROLES = ["admin", "maker", "checker", "viewer", "user"];

export const SERVICES = [
    {
        id: "sql",
        name: "SQL Genie",
        icon: "🧠",
        description:
            "Conversational analytics and natural language data exploration",
        status: SERVICE_STATUS.LIVE,
        url: env.VITE_SQL_GENIE_APP_URL || "http://localhost:8080/",
        // The application shares this platform's token and asks the backend
        // who the person is, so that it decides for itself what they may do.
        session: SESSION_MODE.TOKEN,
    },
    {
        id: "summarizer",
        name: "Data Summarizer",
        icon: "📄",
        description: "PDF, PPT and Excel summarization service",
        status: SERVICE_STATUS.LIVE,
        url: env.VITE_SUMMARIZER_APP_URL || "http://localhost:8090/",
        session: SESSION_MODE.TICKET,
        // Everybody who has signed in may open it. The role inside the service is
        // decided there, and the service keeps its own accounts.
        ownAccounts: true,
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
        // Who may open it is decided by the role in Peer Benchmarking.
        roles: { bench: BENCH_ROLES },
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
        // Who may open it is decided by the role in the News Feed.
        roles: { news: NEWS_ROLES },
    },
];

/**
 * The services a person may open, given the roles they hold.
 *
 * @param {{news?: string, bench?: string}} roles - the roles of the signed-in
 *   person, taken from the `role_news` and `role_bench` columns of the user table.
 */
export function servicesForRoles(roles) {
    const held = roles ?? {};

    return SERVICES.filter((service) => {
        // A service that is not built yet is still listed, and marked as planned.
        if (service.status !== SERVICE_STATUS.LIVE) {
            return true;
        }

        const requirement = service.roles;

        if (!requirement) {
            return true;
        }

        return Object.entries(requirement).every(([column, allowed]) =>
            allowed.includes(held[column]),
        );
    });
}

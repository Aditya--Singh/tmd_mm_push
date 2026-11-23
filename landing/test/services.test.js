import assert from "node:assert/strict";
import { test } from "node:test";

import {
    BENCH_ROLES,
    NEWS_ROLES,
    SERVICE_STATUS,
    SERVICES,
    SESSION_MODE,
    servicesForRoles,
} from "../src/services.js";

function serviceOf(id, services) {
    return services.find((service) => service.id === id);
}

test("the five services that are built are live", () => {
    const services = servicesForRoles({ news: "user", bench: "user" });

    assert.equal(serviceOf("news", services).status, SERVICE_STATUS.LIVE);
    assert.equal(serviceOf("benchmark", services).status, SERVICE_STATUS.LIVE);
    assert.equal(serviceOf("summarizer", services).status, SERVICE_STATUS.LIVE);
    assert.equal(serviceOf("analyzer", services).status, SERVICE_STATUS.LIVE);
    assert.equal(serviceOf("sql", services).status, SERVICE_STATUS.LIVE);
});

test("the SQL Genie is the last card of the rail", () => {
    const services = servicesForRoles({ news: "user", bench: "user" });

    // The order of the rail is the order of this list.
    assert.deepEqual(
        services.map((service) => service.id),
        ["analyzer", "summarizer", "benchmark", "news", "sql"],
    );
});

test("the SQL Genie opens the application it is pointed at", () => {
    const sql = serviceOf(
        "sql",
        servicesForRoles({ news: "user", bench: "user" }),
    );

    // The address may be set in the settings of the landing page, so only the
    // presence of one is checked here.
    assert.ok(sql.url, "the SQL Genie has no address to open");
    assert.equal(sql.session, SESSION_MODE.TOKEN);
});

test("the data analyzer is opened by the role of the news feed", () => {
    const analyzer = serviceOf(
        "analyzer",
        servicesForRoles({ news: "user", bench: "user" }),
    );

    // It keeps its own sessions, so it is given a ticket of its own.
    assert.equal(analyzer.session, SESSION_MODE.TICKET);

    // Who may open it is decided by the role in the News Feed.
    assert.deepEqual(analyzer.roles, { news: NEWS_ROLES });

    // And it has an address to open.
    assert.ok(analyzer.url);
});

test("the data summarizer keeps its own sessions", () => {
    // It has its own accounts, so it is given a ticket of its own rather
    // than the token of this platform.
    const summarizer = serviceOf(
        "summarizer",
        servicesForRoles({ news: "user", bench: "user" }),
    );

    assert.equal(summarizer.session, SESSION_MODE.TICKET);
});

test("the data summarizer is open to everybody who has signed in", () => {
    // It keeps its own accounts and decides the roles there itself.
    const services = servicesForRoles({ bench: "user" });

    assert.ok(serviceOf("summarizer", services));
});

test("the news feed follows the role in the news feed", () => {
    const services = servicesForRoles({ news: "user", bench: "maker" });

    assert.ok(serviceOf("news", services));
});

test("the news feed is not offered without a news role", () => {
    const services = servicesForRoles({ bench: "maker" });

    assert.equal(serviceOf("news", services), undefined);
});

test("peer benchmarking follows the role in peer benchmarking", () => {
    const services = servicesForRoles({ news: "user", bench: "maker" });

    assert.ok(serviceOf("benchmark", services));
});

test("peer benchmarking is not offered without a benchmarking role", () => {
    const services = servicesForRoles({ news: "admin" });

    assert.equal(serviceOf("benchmark", services), undefined);
});

test("every role of each application may open the service that follows it", () => {
    for (const role of NEWS_ROLES) {
        const services = servicesForRoles({ news: role, bench: "user" });

        assert.ok(serviceOf("news", services), `the news feed for ${role}`);
    }

    for (const role of BENCH_ROLES) {
        const services = servicesForRoles({ news: "user", bench: role });

        assert.ok(
            serviceOf("benchmark", services),
            `peer benchmarking for ${role}`,
        );
    }
});

test("a role that is not known opens nothing", () => {
    const services = servicesForRoles({ news: "something-else", bench: "nope" });

    assert.equal(serviceOf("news", services), undefined);
    assert.equal(serviceOf("benchmark", services), undefined);

    // The services that are open to everybody are still listed.
    assert.equal(serviceOf("summarizer", services).status, SERVICE_STATUS.LIVE);
    assert.equal(serviceOf("sql", services).status, SERVICE_STATUS.LIVE);
});

test("every service names the column that decides who may open it", () => {
    for (const service of SERVICES) {
        if (service.status !== SERVICE_STATUS.LIVE) {
            continue;
        }

        // A service either follows a column of this platform's user table, or it
        // decides for itself what the person may do: it either keeps its own
        // accounts, or it shares this platform's token and asks the backend who
        // the person is.
        if (!service.roles) {
            assert.ok(
                service.ownAccounts || service.session === SESSION_MODE.TOKEN,
                `${service.id} names no role column and decides nothing itself`,
            );
            continue;
        }

        for (const column of Object.keys(service.roles)) {
            assert.ok(
                ["news", "bench"].includes(column),
                `${service.id} names an unknown column ${column}`,
            );
        }
    }
});

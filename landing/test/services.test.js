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

test("the three services that are built are live", () => {
    const services = servicesForRoles({ news: "user", bench: "user" });

    assert.equal(serviceOf("news", services).status, SERVICE_STATUS.LIVE);
    assert.equal(serviceOf("benchmark", services).status, SERVICE_STATUS.LIVE);
    assert.equal(serviceOf("summarizer", services).status, SERVICE_STATUS.LIVE);
});

test("the service that is not built yet is marked as planned", () => {
    const services = servicesForRoles({ news: "user", bench: "user" });

    assert.equal(serviceOf("sql", services).status, SERVICE_STATUS.PLANNED);
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

    // The services that are not built yet are still listed.
    assert.equal(serviceOf("sql", services).status, SERVICE_STATUS.PLANNED);
});

test("every service names the column that decides who may open it", () => {
    for (const service of SERVICES) {
        if (service.status !== SERVICE_STATUS.LIVE) {
            continue;
        }

        // A service either follows a column of this platform's user table, or it
        // keeps its own accounts and decides the roles there itself.
        if (!service.roles) {
            assert.ok(
                service.ownAccounts,
                `${service.id} names no role column and does not keep its own accounts`,
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

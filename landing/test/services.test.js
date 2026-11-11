import assert from "node:assert/strict";
import { test } from "node:test";

import {
    BENCH_ROLES,
    NEWS_ROLES,
    SERVICE_STATUS,
    SERVICES,
    servicesForRoles,
} from "../src/services.js";

function serviceOf(id, services) {
    return services.find((service) => service.id === id);
}

test("the two services that are built are live", () => {
    const services = servicesForRoles({ news: "user", bench: "user" });

    assert.equal(serviceOf("news", services).status, SERVICE_STATUS.LIVE);
    assert.equal(serviceOf("benchmark", services).status, SERVICE_STATUS.LIVE);
});

test("the two services that are not built yet are marked as planned", () => {
    const services = servicesForRoles({ news: "user", bench: "user" });

    assert.equal(serviceOf("sql", services).status, SERVICE_STATUS.PLANNED);
    assert.equal(serviceOf("summarizer", services).status, SERVICE_STATUS.PLANNED);
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

        assert.ok(service.roles, `${service.id} names no role column`);

        for (const column of Object.keys(service.roles)) {
            assert.ok(
                ["news", "bench"].includes(column),
                `${service.id} names an unknown column ${column}`,
            );
        }
    }
});

import assert from "node:assert/strict";
import { test } from "node:test";

import {
    apiAddress,
    describeLoginFailure,
    proxyTarget,
} from "../src/api/loginError.js";

function failure(status, data = null) {
    const error = new Error("request failed");

    if (status) {
        error.response = { status, data };
    }

    return error;
}

test("the address of the request is named", () => {
    assert.equal(
        apiAddress("", "http://localhost:5174"),
        "http://localhost:5174",
    );

    assert.equal(
        apiAddress("http://127.0.0.1:8000/", "http://localhost:5174"),
        "http://127.0.0.1:8000",
    );
});

test("the address never carries a trailing slash", () => {
    assert.equal(proxyTarget("http://127.0.0.1:8000/"), "http://127.0.0.1:8000");
    assert.equal(proxyTarget(""), "");
});

test("wrong credentials are said plainly", () => {
    const described = describeLoginFailure(failure(401));

    assert.equal(described.message, "Invalid username or password.");
    assert.equal(described.detail, "");
});

test("a backend that is not running is named", () => {
    const described = describeLoginFailure(failure(502), {
        proxyTarget: "http://127.0.0.1:8000",
    });

    assert.match(described.message, /backend is not answering/);
    assert.match(described.detail, /uvicorn/);
    assert.match(described.detail, /127\.0\.0\.1:8000/);
});

test("a request that never arrives says where it was sent", () => {
    const described = describeLoginFailure(failure(null), {
        baseUrl: "",
        origin: "http://localhost:5174",
    });

    assert.match(described.message, /could not reach/);
    assert.match(described.detail, /http:\/\/localhost:5174/);
    assert.match(described.detail, /VITE_API_BASE_URL/);
    assert.match(described.detail, /CORS_ORIGINS/);
});

test("an answer from the backend is passed on", () => {
    const described = describeLoginFailure(failure(500, { detail: "Boom" }));

    assert.match(described.message, /500/);
    assert.equal(described.detail, "Boom");
});

test("every failure has something to read", () => {
    for (const status of [401, 403, 500, 502, 503, null]) {
        const described = describeLoginFailure(failure(status));

        assert.ok(described.message, `nothing said for ${status}`);
    }
});

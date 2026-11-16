import assert from "node:assert/strict";
import { test } from "node:test";

// The client reads the session from the browser, so the browser is faked first.
globalThis.window = {
    localStorage: {
        getItem: () => null,
        setItem: () => {},
        removeItem: () => {},
    },
};

const { default: apiClient } = await import("../src/api/client.js");

/**
 * A stand-in for the server: the first calls fail, the later ones answer.
 */
function failingServer(statuses) {
    const calls = [];

    apiClient.defaults.adapter = async (config) => {
        calls.push(config.url);

        const status = statuses[Math.min(calls.length - 1, statuses.length - 1)];

        if (status >= 400) {
            const error = new Error(`the server answered ${status}`);

            error.response = { status, data: { detail: "not yet" } };
            error.config = config;
            error.isAxiosError = true;

            throw error;
        }

        return {
            data: { ok: true },
            status,
            statusText: "OK",
            headers: {},
            config,
        };
    };

    return calls;
}

test("a service that has just been started is tried once more", async () => {
    const calls = failingServer([503, 200]);

    const response = await apiClient.get("/api/services/summarizer/manifest");

    assert.equal(response.data.ok, true);
    assert.equal(calls.length, 2, "the call was made twice");
});

test("a refusal from the server is not tried again", async () => {
    const calls = failingServer([401]);

    await assert.rejects(() => apiClient.get("/api/auth/me"));

    assert.equal(calls.length, 1, "the call was made once");
});

test("a service that stays down gives up after the second try", async () => {
    const calls = failingServer([503]);

    await assert.rejects(() => apiClient.get("/api/services/summarizer/manifest"));

    assert.equal(calls.length, 2, "the call was made twice");
});

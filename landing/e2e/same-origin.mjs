/**
 * The check of the production layout.
 *
 * In production everything is served from one address: the landing page, the news
 * application and the API. A small reverse proxy stands in for the web server, so
 * that the arrangement can be exercised without setting one up.
 *
 * The proxy is started here and stopped at the end. The static builds of the two
 * web applications have to be there, so `npm run build` is run first:
 *
 *     cd landing && npm run build
 *     cd frontend && npm run build
 *
 * The backend of the hub has to be running, and so do Peer Benchmarking, the Data
 * Summarizer and the Data Analyzer.
 */
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..", "..");

const HUB_DIST = process.env.HUB_DIST || join(ROOT, "landing", "dist");
const NEWS_DIST = process.env.NEWS_DIST || join(ROOT, "frontend", "dist");
const API_TARGET = process.env.API_TARGET || "http://127.0.0.1:8000";
const PORT = Number(process.env.PORT || 5175);
const PROXY_URL = `http://127.0.0.1:${PORT}/`;

const USERNAME = process.env.E2E_USERNAME || "admin";
const PASSWORD = process.env.E2E_PASSWORD || "admin@tmd26";

let failures = 0;

function check(name, ok, detail = "") {
    if (!ok) failures += 1;

    console.log(`${ok ? "PASS" : "FAIL"} - ${name}${detail ? `  ::  ${detail}` : ""}`);
}

// The interface of the news application is built into the static folder. Without it
// there is nothing to show, and the check would fail for the wrong reason.
for (const folder of [HUB_DIST, NEWS_DIST]) {
    if (!existsSync(join(folder, "index.html"))) {
        console.error(`The static build is missing: ${folder}`);
        console.error("Run 'npm run build' in landing/ and in frontend/ first.");
        process.exit(1);
    }
}

// ------------------------------------------------------------------
// The reverse proxy
// ------------------------------------------------------------------

const proxy = spawn(
    process.execPath,
    [join(HERE, "same-origin-proxy.mjs")],
    {
        env: {
            ...process.env,
            HUB_DIST,
            NEWS_DIST,
            API_TARGET,
            PORT: String(PORT),
        },
        stdio: ["ignore", "pipe", "pipe"],
    },
);

let proxyOutput = "";

proxy.stdout.on("data", (chunk) => (proxyOutput += chunk));
proxy.stderr.on("data", (chunk) => (proxyOutput += chunk));

// The browser is closed and the proxy is stopped whatever happens.
function stop() {
    proxy.kill();
}

process.on("exit", stop);
process.on("SIGINT", () => {
    stop();
    process.exit(130);
});

// Wait for the proxy to answer before the browser is sent to it.
let up = false;

for (let attempt = 0; attempt < 30; attempt += 1) {
    try {
        const answer = await fetch(PROXY_URL, { signal: AbortSignal.timeout(2000) });

        if (answer.ok) {
            up = true;
            break;
        }
    } catch {
        /* not yet */
    }

    await new Promise((resolveWait) => setTimeout(resolveWait, 500));
}

if (!up) {
    console.error("The reverse proxy did not come up.");
    console.error(proxyOutput);
    process.exit(1);
}

console.log(`The proxy is serving one address: ${PROXY_URL}`);

// ------------------------------------------------------------------
// The browser
// ------------------------------------------------------------------

const browser = await chromium.launch({
    ...(process.env.CHROME_BIN ? { executablePath: process.env.CHROME_BIN } : {}),
    args: ["--no-sandbox", "--disable-dev-shm-usage"],
});

const context = await browser.newContext({ viewport: { width: 1500, height: 940 } });
const page = await context.newPage();

const consoleErrors = [];
const requested = [];

page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
});
page.on("pageerror", (error) => consoleErrors.push(String(error)));
page.on("request", (request) => requested.push(request.url()));

await page.goto(PROXY_URL, { waitUntil: "networkidle" });

check(
    "the landing page is served from the one address",
    await page.locator(".login-button").isVisible(),
);

// The API is answered by the backend behind the same address.
const apiAnswer = await page.evaluate(async () => {
    const answer = await fetch("/api/auth/me");

    return answer.status;
});

check(
    "the API is answered on the same address",
    apiAnswer === 401 || apiAnswer === 200,
    String(apiAnswer),
);

await page.fill("#username", USERNAME);
await page.fill("#password", PASSWORD);
await page.click(".login-button");

await page.waitForSelector(".header-avatar", { timeout: 20000 });

check("the person is signed in on one address", true);

// The news application is framed from the same address as well.
const newsCard = page.locator(".app-card", { hasText: "News Feed" });

check("the hub offers the news application", (await newsCard.count()) === 1);

await newsCard.click();

const frame = page.frameLocator(".workspace-frame iframe");

await frame.locator(".dashboard").first().waitFor({ timeout: 25000 });
await page.waitForTimeout(2000);

const newsFrame = page.frames().find((f) => f.url().includes(String(PORT)));

check("the news application opens in the workspace", newsFrame !== undefined);

check(
    "the news application shows no sign-in form of its own",
    (await frame.locator(".login-button").count()) === 0 &&
        (await frame.locator('input[type="password"]').count()) === 0,
);

// The session must be the one of the hub: the frame holds the token the hub gave
// it, and the API answers for the same person.
const stored = await newsFrame.evaluate(() =>
    localStorage.getItem("bankNewsUser"),
);

check(
    "the session was handed over and stored in the frame",
    Boolean(stored) && stored.includes("accessToken"),
    stored ? "token present" : "no session stored",
);

const who = await newsFrame.evaluate(async () => {
    const session = JSON.parse(localStorage.getItem("bankNewsUser") || "{}");

    const answer = await fetch("/api/auth/me", {
        headers: { Authorization: `Bearer ${session.accessToken || ""}` },
    });

    return answer.ok ? await answer.json() : { error: answer.status };
});

check(
    "the news application knows the person",
    who?.username === USERNAME,
    JSON.stringify(who),
);

// Nothing may be loaded from another address: that is the point of the arrangement.
const foreign = requested.filter(
    (url) => !url.startsWith(PROXY_URL) && !url.startsWith(API_TARGET),
);

check(
    "nothing is loaded from another address",
    foreign.length === 0,
    foreign.join(" | "),
);

const unexpected = consoleErrors.filter((e) => !e.includes("401 (Unauthorized)"));

check("no errors in the browser console", unexpected.length === 0, unexpected.join(" | "));

await browser.close();
stop();

console.log("");
console.log("Checks: " + (failures ? failures + " failed" : "all passed"));

process.exit(failures ? 1 : 0);

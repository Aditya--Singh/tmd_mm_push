import { chromium } from "playwright";

const HUB_URL = process.env.HUB_URL || "http://localhost:5174/";
const USERNAME = process.env.E2E_USERNAME || "admin";
const PASSWORD = process.env.E2E_PASSWORD || "admin@tmd26";
const FRAME_MATCH = process.env.E2E_FRAME_MATCH || "5173";

const results = [];

function check(name, ok, detail = "") {
    results.push({ name, ok });
    console.log(
        `${ok ? "PASS" : "FAIL"} - ${name}${detail ? `  ::  ${detail}` : ""}`,
    );
}

// CHROME_BIN lets a machine without the default browser build point at
// its own copy of Chromium.
const browser = await chromium.launch(
    process.env.CHROME_BIN ? { executablePath: process.env.CHROME_BIN } : {},
);
const context = await browser.newContext();
const page = await context.newPage();

const consoleErrors = [];
const apiResponses = [];

page.on("console", (message) => {
    if (message.type() === "error") {
        consoleErrors.push(message.text());
    }
});

page.on("pageerror", (error) => {
    consoleErrors.push(String(error));
});

page.on("response", (response) => {
    const url = response.url();

    if (url.includes("/api/news") || url.includes("/api/dashboard")) {
        apiResponses.push({ url, status: response.status() });
    }
});

// ------------------------------------------------------------------
// 1. The landing page asks for credentials before showing the hub
// ------------------------------------------------------------------

await page.goto(HUB_URL, { waitUntil: "networkidle" });

check(
    "landing page shows a sign-in screen",
    await page.locator(".login-button").isVisible(),
);

check(
    "no service is embedded before sign-in",
    (await page.locator(".workspace-frame iframe").count()) === 0,
);

// ------------------------------------------------------------------
// 2. Signing in opens the hub
// ------------------------------------------------------------------

await page.fill("#username", USERNAME);
await page.fill("#password", PASSWORD);
await page.click(".login-button");

await page.waitForSelector(".header-avatar", { timeout: 20000 });

check(
    "hub shell is rendered after sign-in",
    await page.locator(".platform-title").isVisible(),
);

const userName = (await page.locator(".header-user-info strong").innerText()).trim();
check("signed-in user is shown", userName === USERNAME, userName);

const cardCount = await page.locator(".app-card").count();
check("all four intelligence services are listed", cardCount === 4, `${cardCount}`);

check(
    "the SQL Genie is not offered at the moment",
    (await page.locator(".app-card", { hasText: "SQL Genie" }).count()) === 0,
);

check(
    "Peer Benchmarking is no longer marked as planned",
    !(await page
        .locator(".app-card", { hasText: "Peer Benchmarking" })
        .locator(".app-badge")
        .count()),
);

const headerButtons = await page.locator(".header-actions button").allInnerTexts();

check(
    "the landing page header carries the feedback and logout controls",
    headerButtons.some((label) => label.includes("Give Feedback")) &&
        headerButtons.some((label) => label.includes("Logout")),
    headerButtons.join(", "),
);

check(
    "the landing page header shows the current date",
    /\d{2} \w{3} \d{4}/.test(
        await page.locator(".header-date").innerText(),
    ),
    await page.locator(".header-date").innerText(),
);

check(
    "the landing page header greets the signed-in user",
    (await page.locator(".header-user-info strong").innerText()).trim() ===
        USERNAME,
);

check(
    "the landing page header shows the user avatar",
    (await page.locator(".header-avatar").innerText()).trim() ===
        USERNAME.charAt(0).toUpperCase(),
);

// ------------------------------------------------------------------
// The service rail can be collapsed to the left
// ------------------------------------------------------------------

const expandedWidth = await page
    .locator(".sidebar")
    .evaluate((element) => element.getBoundingClientRect().width);

check(
    "the service rail starts expanded",
    expandedWidth > 200,
    `${Math.round(expandedWidth)}px`,
);

await page.locator(".sidebar-toggle").click();
await page.waitForTimeout(500);

const collapsedWidth = await page
    .locator(".sidebar")
    .evaluate((element) => element.getBoundingClientRect().width);

check(
    "the service rail collapses towards the left edge",
    collapsedWidth < expandedWidth,
    `${Math.round(expandedWidth)}px -> ${Math.round(collapsedWidth)}px`,
);

check(
    "the collapsed rail keeps the service names",
    (await page.locator(".app-card .app-name").count()) === 4,
);

check(
    "the collapsed rail hides the service descriptions",
    !(await page.locator(".app-card .app-desc").first().isVisible()),
);

check(
    "the collapse toggle reports the state",
    (await page.locator(".sidebar-toggle").getAttribute("aria-expanded")) ===
        "false",
);

// The choice is remembered.
await page.reload({ waitUntil: "networkidle" });
await page.waitForSelector(".header-avatar", { timeout: 20000 });

const widthAfterReload = await page
    .locator(".sidebar")
    .evaluate((element) => element.getBoundingClientRect().width);

check(
    "the collapsed state is remembered",
    Math.abs(widthAfterReload - collapsedWidth) < 2,
    `${Math.round(widthAfterReload)}px`,
);

await page.locator(".sidebar-toggle").click();
await page.waitForTimeout(500);

check(
    "the rail expands again",
    (await page
        .locator(".sidebar")
        .evaluate((element) => element.getBoundingClientRect().width)) >
        200,
);

const plannedBadge = await page
    .locator(".app-card", { hasText: "Data Analyzer" })
    .locator(".app-badge")
    .count();
check(
    "a service that is built is not marked as planned",
    plannedBadge === 0,
    `${plannedBadge} badges`,
);

// ------------------------------------------------------------------
// 3. The SQL Genie is kept, but is not offered
// ------------------------------------------------------------------

check(
    "the SQL Genie has no card in the rail",
    (await page.locator(".app-card", { hasText: "SQL Genie" }).count()) === 0,
);

// ------------------------------------------------------------------
// 4. The news feed opens inside the workspace, already signed in
// ------------------------------------------------------------------

await page.locator(".app-card", { hasText: "News Feed" }).click();
await page.waitForSelector(".workspace-frame iframe", { timeout: 20000 });

const frame = page.frameLocator(".workspace-frame iframe");

await frame.locator(".dashboard").waitFor({ timeout: 25000 });

check(
    "the embedded application renders the dashboard, not a sign-in screen",
    (await frame.locator(".login-button").count()) === 0,
);

check(
    "the embedded application shows no header of its own",
    (await frame.locator("header.header").count()) === 0 &&
        (await frame.locator(".embedded-toolbar").count()) === 0,
);

const childFrame = page.frames().find((f) => f.url().includes(FRAME_MATCH));
check("the embedded frame was located", Boolean(childFrame));

if (childFrame) {
    const stored = await childFrame.evaluate(() =>
        localStorage.getItem("bankNewsUser"),
    );

    check(
        "the session was handed over and stored in the frame",
        Boolean(stored) && stored.includes("accessToken"),
        stored ? "token present" : "no session stored",
    );

    const hubStored = await page.evaluate(() =>
        localStorage.getItem("bankHubSession"),
    );

    check(
        "the landing page keeps its own session",
        Boolean(hubStored) && hubStored.includes("accessToken"),
    );
}

// ------------------------------------------------------------------
// 5. The news pipeline asks how far back the news may reach
// ------------------------------------------------------------------

// The administrator of the News Feed holds the pipeline control.
await frame.locator(".admin-tabs").first().waitFor({ timeout: 25000 });

const windows = (
    await frame.locator(".pipeline-window select option").allInnerTexts()
).map((label) => label.trim());

check(
    "the news pipeline offers a window of days, up to ninety",
    windows.length > 0 &&
        windows.includes("Last 90 days") &&
        windows.includes("Last 30 days"),
    windows.join(", "),
);

const noteBefore = (
    await frame.locator(".pipeline-note").innerText()
).trim();

await frame.locator(".pipeline-window select").selectOption("90");
await page.waitForTimeout(400);

const noteAfter = (await frame.locator(".pipeline-note").innerText()).trim();

check(
    "choosing a window changes the date the news is stored from",
    noteBefore !== noteAfter && noteAfter.includes("stored"),
    `${noteBefore} -> ${noteAfter}`,
);

// The frame must be able to call the API with the transferred token.
const newsCalls = apiResponses.filter((entry) =>
    entry.url.includes("/api/news"),
);

check(
    "the embedded application can read the news API with the transferred token",
    newsCalls.length > 0 && newsCalls.every((entry) => entry.status === 200),
    newsCalls.map((entry) => entry.status).join(",") || "no calls seen",
);

check(
    "the embedded application is never rejected as unauthorised",
    !apiResponses.some((entry) => entry.status === 401),
);

// The feedback the landing page collects must reach the backend.
let feedbackStatus = null;

page.on("response", (response) => {
    if (response.url().includes("/api/feedback")) {
        feedbackStatus = response.status();
    }
});

await page.locator(".feedback-header-button").click();
await page.waitForSelector(".feedback-modal", { timeout: 10000 });

const ratingRows = await page.locator(".feedback-rating-row").all();

for (const row of ratingRows) {
    await row.locator(".star").nth(3).click();
}

await page.fill("#feedback-comments", "Verification of the feedback flow.");

await page.locator(".feedback-button.primary").click();
await page.waitForSelector(".feedback-modal", {
    state: "detached",
    timeout: 10000,
});

check(
    "the landing page can submit feedback with its own session",
    feedbackStatus === 201,
    `status=${feedbackStatus}`,
);

// ------------------------------------------------------------------
// 5. An expired session in the frame signs the user out of the hub
// ------------------------------------------------------------------

if (childFrame) {
    await childFrame.evaluate(() => {
        window.dispatchEvent(new Event("auth-expired"));
    });

    await page.waitForSelector(".login-button", { timeout: 15000 });

    check(
        "an expired session in the embedded application returns the hub to the sign-in screen",
        await page.locator(".login-button").isVisible(),
    );
} else {
    check("an expired session in the embedded application returns the hub to the sign-in screen", false, "no frame");
}

// ------------------------------------------------------------------
// 6. Signing out of the hub removes the embedded application
// ------------------------------------------------------------------

await page.fill("#username", USERNAME);
await page.fill("#password", PASSWORD);
await page.click(".login-button");
await page.waitForSelector(".header-avatar", { timeout: 20000 });

await page.locator(".app-card", { hasText: "News Feed" }).click();
await page.waitForSelector(".workspace-frame iframe", { timeout: 20000 });

// Wait for the embedded application to be ready before signing out, as
// a user would.
await page
    .frameLocator(".workspace-frame iframe")
    .locator(".dashboard")
    .waitFor({ timeout: 25000 });

await page.locator(".logout-btn").click();
await page.waitForSelector(".login-button", { timeout: 15000 });

check(
    "signing out of the hub returns to the sign-in screen",
    await page.locator(".login-button").isVisible(),
);

check(
    "signing out of the hub removes the embedded application",
    (await page.locator(".workspace-frame iframe").count()) === 0,
);

// The embedded application keeps its own copy of the session, because it
// usually runs on a different origin. It must be cleared too, otherwise
// the dashboard stays signed in when it is opened directly.
const storageState = await context.storageState();

const childOriginState = storageState.origins.find((entry) =>
    entry.origin.includes(FRAME_MATCH),
);

const childSession = childOriginState?.localStorage?.find(
    (entry) => entry.name === "bankNewsUser",
);


check(
    "signing out of the hub also clears the session inside the embedded application",
    !childSession,
    childSession ? "session still present" : "cleared",
);

const hubStoredAfter = await page.evaluate(() =>
    localStorage.getItem("bankHubSession"),
);

check(
    "signing out clears the stored session",
    hubStoredAfter === null,
);

await browser.close();

// ------------------------------------------------------------------

const failed = results.filter((result) => !result.ok);

console.log("");
console.log(`Checks: ${results.length}, failed: ${failed.length}`);

if (consoleErrors.length > 0) {
    console.log("");
    console.log("Browser console errors:");
    for (const error of consoleErrors) {
        console.log(`  - ${error}`);
    }
}

if (failed.length > 0) {
    console.log("");
    console.log("Failed checks:");
    for (const result of failed) {
        console.log(`  - ${result.name}`);
    }

    process.exit(1);
}

// End-to-end check of the hub with the Data Analyzer in its workspace.
//
// The hub signs the person in, opens the Data Analyzer, and the analyzer must be signed
// in too, as the same person, with the role the person holds in the News Feed.
import { chromium } from 'playwright';

const HUB = process.env.HUB_URL || 'http://127.0.0.1:5174/';
const USER = process.env.E2E_USER || 'analyst';
const PASS = process.env.E2E_PASS || 'Pnb@12345';

// The role the person holds in the News Feed. The hub states it, and the analyzer is
// given the same one.
const EXPECTED_ROLE = process.env.E2E_ROLE || 'user';

const browser = await chromium.launch({
    ...(process.env.CHROME_BIN ? { executablePath: process.env.CHROME_BIN } : {}),
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

const ctx = await browser.newContext({ viewport: { width: 1500, height: 940 } });
const page = await ctx.newPage();

const errors = [];
page.on('console', (m) => {
    if (m.type() === 'error') errors.push(m.text());
});
page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));

// The app swaps the hub's ticket for a token of its own, and that token is what its
// API calls carry. It is taken from the exchange itself, so the check speaks to the
// app the way the app speaks to itself.
let accessToken = '';
page.on('response', async (response) => {
    if (!response.url().includes('/api/auth/exchange') || !response.ok()) return;
    try {
        accessToken = (await response.json()).access_token || '';
    } catch {
        /* the body was already taken */
    }
});

let failures = 0;
function check(label, condition, detail = '') {
    if (condition) {
        console.log('PASS - ' + label);
    } else {
        failures += 1;
        console.log('FAIL - ' + label + (detail ? '  ::  ' + detail : ''));
    }
}

await page.goto(HUB, { waitUntil: 'networkidle' });

await page.fill('#username', USER);
await page.fill('#password', PASS);
await page.click('button[type="submit"]');
await page.waitForSelector('.hub', { timeout: 15000 });
check('the hub signs the person in', true);

// The card of the analyzer must be there, and must not say "planned".
const card = page.locator('.app-card', { hasText: 'Data Analyzer' });
check('the hub offers the Data Analyzer', (await card.count()) === 1);

const cardText = (await card.textContent()) || '';
check(
    'the Data Analyzer is not marked as planned',
    !cardText.toLowerCase().includes('planned'),
    cardText.trim().slice(0, 120),
);

await card.click();

const frame = page.frameLocator('iframe');

// The app must come up signed in, with no sign-in form of its own.
await frame.locator('body').first().waitFor({ timeout: 25000 });
await page.waitForTimeout(3000);

check('the analyzer opens inside the workspace', true);

const appFrame = page.frames().find((f) => f.url().includes('8095'));
check('the frame of the analyzer is there', appFrame !== undefined);

const hasPasswordField = await frame.locator('input[type="password"]').count();
check('the analyzer shows no sign-in form', hasPasswordField === 0);

// The identity and the role must have travelled with the sign-in.
const who = await appFrame.evaluate(async (token) => {
    const response = await fetch('/api/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
    });
    return response.ok ? await response.json() : { error: response.status };
}, accessToken);

check('the analyzer knows the person', who?.username === USER, JSON.stringify(who));
check(
    'the analyzer signed the person in as the right person',
    who?.username === USER,
    who?.username,
);
check(
    'the analyzer gave the person the role it holds in the News Feed',
    who?.role === EXPECTED_ROLE,
    who?.role + ' (expected ' + EXPECTED_ROLE + ')',
);

// The hub's rail must offer the tools of the analyzer.
const sections = (await page.locator('.app-section').allTextContents()).map((s) =>
    s.trim(),
);
check(
    'the hub rail offers the four tools of the analyzer',
    JSON.stringify(sections) ===
        JSON.stringify(['Proofread', 'Rewrite', 'Summarize', 'Ask about data']),
    JSON.stringify(sections),
);

check(
    'the rail no longer offers the screens that were taken out',
    !sections.some((s) => /circular|soon/i.test(s)),
    JSON.stringify(sections),
);

// Choosing a tool in the rail must move the app to it.
await page.locator('.app-section', { hasText: 'Summarize' }).click();
await page.waitForTimeout(2500);

const onSummarize = await appFrame.evaluate(() => location.hash);
check(
    'choosing a tool in the rail moves the app to it',
    onSummarize === '#/summarize',
    onSummarize,
);

// The app itself must show that tool, and not only change its address.
const shownTool = await appFrame.evaluate(() => {
    const chosen = Array.from(
        document.querySelectorAll('[role="radio"][aria-checked="true"]'),
    ).map((b) => (b.textContent || '').trim());

    return chosen.join(', ');
});
check(
    'the app shows the tool that was chosen in the rail',
    shownTool === 'Summarize',
    shownTool,
);

// The app must not show the block of the old tab bar.
const appText = await appFrame.evaluate(() => document.body.innerText);
check(
    'the app shows no tab bar of its own',
    !/Document Assistant|Circular Analyzer|Coming Soon/.test(appText),
    appText.slice(0, 160),
);

// The app must not show a banner of its own either: the hub draws the chrome.
check(
    'the app shows no banner of its own',
    !/Employee Productivity Tool/.test(appText),
    appText.slice(0, 160),
);

// The view must begin with the four tools.
const firstRow = await appFrame.evaluate(() => {
    const main = document.querySelector('main');
    if (!main) return '';

    const row = main.querySelector('div');
    if (!row) return '';

    return Array.from(row.querySelectorAll('[role="radio"]'))
        .map((b) => (b.textContent || '').trim())
        .join(', ');
});
check(
    'the view begins with the four tools',
    firstRow === 'Proofread, Rewrite, Summarize, Ask about data',
    firstRow,
);

check(
    'the app still says whether the services are online',
    /Services online|Checking services|Backend offline/.test(appText),
    appText.slice(0, 160),
);

// Choosing a tool inside the app must move the rail of the hub.
await appFrame.locator('[role="radio"]', { hasText: 'Rewrite' }).click();
await page.waitForTimeout(2500);

const railFollows = await page
    .locator('.app-section.active .app-section-name')
    .innerText();
check(
    'choosing a tool in the app moves the rail of the hub',
    railFollows.trim() === 'Rewrite',
    railFollows,
);

await page.screenshot({ path: '/workspace/analyzer-rail.png' });

// A reader may not delete a document; the app must refuse it.
const refused = await appFrame.evaluate(async (token) => {
    const response = await fetch('/api/document-assistant/files/nope', {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
    });
    return response.status;
}, accessToken);
check('a reader may not delete a document', refused === 403, String(refused));

// Signing out of the hub must end the session in the app too.
await page.evaluate(() => {
    window.__hubLogoutAck = false;

    window.addEventListener('message', (event) => {
        if (event.data?.type === 'hubint:logout-ack') {
            window.__hubLogoutAck = true;
        }
    });
});

await page.locator('.logout-btn').click();
await page.waitForTimeout(2500);

const ack = await page.evaluate(() => window.__hubLogoutAck === true);
check('the analyzer confirms the sign-out', ack === true);

await page.waitForTimeout(2000);

const frameGone = page.frames().find((f) => f.url().includes('8095')) === undefined;
check('the hub closes the workspace once the app has signed out', frameGone);

const backToLogin = await page.locator('.login-page').count();
check('the hub returns to its sign-in screen', backToLogin === 1);

// The refusal of the reader was asked for on purpose, and the browser writes it
// into the console. Nothing else may be there.
const unexpected = errors.filter((e) => !e.includes('403 (Forbidden)'));
check('no errors in the browser console', unexpected.length === 0, unexpected.join(' | '));

console.log('');
console.log('Checks: ' + (failures ? failures + ' failed' : 'all passed'));

await browser.close();

process.exit(failures ? 1 : 0);

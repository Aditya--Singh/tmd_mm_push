// End-to-end check of the hub with Peer Benchmarking in its workspace.
//
// The hub signs the person in, opens Peer Benchmarking, and the
// benchmarking app must be signed in too, with the role the hub holds.
import { chromium } from 'playwright';

const HUB = process.env.HUB_URL || 'http://127.0.0.1:5174/';
const USER = process.env.E2E_USER || 'analyst';
const PASS = process.env.E2E_PASS || 'Analyst@news26';
const EXPECTED_ROLE = process.env.E2E_ROLE || 'maker';

// CHROME_BIN lets a machine without the default browser build point at
// its own copy of Chromium.
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

await page.locator('.app-card', { hasText: 'Peer Benchmarking' }).click();

const frame = page.frameLocator('iframe');

// The app must come up signed in, with no sign-in form of its own.
await frame.locator('.page').first().waitFor({ timeout: 25000 });
check('the benchmarking app opens inside the workspace', true);

const loginForm = await frame.locator('.login-form').count();
check('the benchmarking app shows no sign-in form', loginForm === 0);

// The role must have travelled with the sign-in.
const appFrame = page.frames().find((f) => f.url().includes('8077'));
const who = await appFrame.evaluate(() => {
    const btn = document.querySelector('.user-btn');
    return btn ? btn.textContent : '';
});
check(
    'the benchmarking app shows the role it was signed in with',
    who.toLowerCase().includes(EXPECTED_ROLE),
    who,
);

// The hub's rail must offer the screens of the benchmarking app.
const sections = (await page.locator('.app-section').allTextContents()).map((s) =>
    s.trim(),
);
check(
    'the hub rail offers the screens of the benchmarking app',
    sections.length === 7 && sections[0] === 'Overview',
    JSON.stringify(sections),
);

// Choosing a screen in the rail must move the app to it.
await page.locator('.app-section', { hasText: 'Trends' }).click();
await page.waitForTimeout(2500);

const onTrends = await appFrame.evaluate(() => location.hash);
check('choosing a screen in the rail moves the app to it', onTrends.includes('trends'), onTrends);

await page.screenshot({ path: '/workspace/bench-trends.png' });

// Signing out of the hub must end the session in the app too. The app
// confirms it, and the hub then removes the frame.
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

check('the benchmarking app confirms the sign-out', ack === true);

await page.waitForTimeout(2000);

const frameGone = page.frames().find((f) => f.url().includes('8077')) === undefined;
check('the hub closes the workspace once the app has signed out', frameGone);

const backToLogin = await page.locator('.login-page').count();
check('the hub returns to its sign-in screen', backToLogin === 1);

check('no errors in the browser console', errors.length === 0, errors.join(' | '));

console.log('');
console.log('Checks: ' + (failures ? failures + ' failed' : 'all passed'));

await browser.close();

process.exit(failures ? 1 : 0);

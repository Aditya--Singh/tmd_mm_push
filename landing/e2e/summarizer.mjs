// End-to-end check of the hub with the Data Summarizer in its workspace.
//
// The hub signs the person in, opens the Data Summarizer, and the summarizer
// must be signed in too, as the same person.
import { chromium } from 'playwright';

const HUB = process.env.HUB_URL || 'http://127.0.0.1:5174/';
const USER = process.env.E2E_USER || 'analyst';
const PASS = process.env.E2E_PASS || 'Pnb@12345';

// The role the summarizer gives the person. The hub names who the person is;
// the summarizer decides what they may do there.
const EXPECTED_ROLE = process.env.E2E_ROLE || 'analyst';

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

// The card of the summarizer must be there, and must not say "planned".
const card = page.locator('.app-card', { hasText: 'Data Summarizer' });
check('the hub offers the Data Summarizer', (await card.count()) === 1);

const cardText = (await card.textContent()) || '';
check(
    'the Data Summarizer is not marked as planned',
    !cardText.toLowerCase().includes('planned'),
    cardText.trim().slice(0, 120),
);

await card.click();

const frame = page.frameLocator('iframe');

// The app must come up signed in, with no sign-in form of its own.
await frame.locator('body').first().waitFor({ timeout: 25000 });
await page.waitForTimeout(3000);

check('the summarizer opens inside the workspace', true);

const appFrame = page.frames().find((f) => f.url().includes('8090'));
check('the frame of the summarizer is there', appFrame !== undefined);

const hasPasswordField = await frame.locator('input[type="password"]').count();
check('the summarizer shows no sign-in form', hasPasswordField === 0);

// The identity must have travelled with the sign-in.
const who = await appFrame.evaluate(async () => {
    const token = localStorage.getItem('sentinel.token');
    const response = await fetch('/api/auth/me', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return response.ok ? await response.json() : { error: response.status, hasToken: !!token };
});

check('the summarizer knows the person', who !== null, JSON.stringify(who));
check(
    'the summarizer signed the person in as the right person',
    who?.email === USER + '@hub.local',
    who?.email,
);
check(
    'the summarizer gave the person the role it decides',
    who?.role === EXPECTED_ROLE,
    who?.role + ' (expected ' + EXPECTED_ROLE + ')',
);

// The hub's rail must offer the screens of the summarizer.
const sections = (await page.locator('.app-section').allTextContents()).map((s) =>
    s.trim(),
);
check(
    'the hub rail offers the screens of the summarizer',
    sections.length >= 6 && sections[0] === 'Overview',
    JSON.stringify(sections),
);

// Choosing a screen in the rail must move the app to it.
await page.locator('.app-section', { hasText: 'Circulars' }).click();
await page.waitForTimeout(2500);

const onCirculars = await appFrame.evaluate(() => location.pathname);
check(
    'choosing a screen in the rail moves the app to it',
    onCirculars.includes('/circulars'),
    onCirculars,
);

await page.screenshot({ path: '/workspace/summarizer-circulars.png' });

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

check('the summarizer confirms the sign-out', ack === true);

await page.waitForTimeout(2000);

const frameGone = page.frames().find((f) => f.url().includes('8090')) === undefined;
check('the hub closes the workspace once the app has signed out', frameGone);

const backToLogin = await page.locator('.login-page').count();
check('the hub returns to its sign-in screen', backToLogin === 1);

check('no errors in the browser console', errors.length === 0, errors.join(' | '));

console.log('');
console.log('Checks: ' + (failures ? failures + ' failed' : 'all passed'));

await browser.close();

process.exit(failures ? 1 : 0);

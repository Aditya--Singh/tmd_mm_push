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
const who = await appFrame.evaluate(async () => {
    const response = await fetch('/api/auth/me');
    return response.ok ? await response.json() : { error: response.status };
});

check('the analyzer knows the person', who !== null, JSON.stringify(who));
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

// The hub's rail must offer the screens of the analyzer.
const sections = (await page.locator('.app-section').allTextContents()).map((s) =>
    s.trim(),
);
check(
    'the hub rail offers the screens of the analyzer',
    sections.length >= 3 && sections[0] === 'Document Assistant',
    JSON.stringify(sections),
);

// Choosing a screen in the rail must move the app to it.
await page.locator('.app-section', { hasText: 'Circular Analyzer' }).click();
await page.waitForTimeout(2500);

const onCircular = await appFrame.evaluate(() => location.hash);
check(
    'choosing a screen in the rail moves the app to it',
    onCircular.includes('circular-analyzer'),
    onCircular,
);

await page.screenshot({ path: '/workspace/analyzer-circular.png' });

// A reader may not delete a document; the app must refuse it.
const refused = await appFrame.evaluate(async () => {
    const response = await fetch('/api/document-assistant/files/nope', {
        method: 'DELETE',
    });
    return response.status;
});
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

check('no errors in the browser console', errors.length === 0, errors.join(' | '));

console.log('');
console.log('Checks: ' + (failures ? failures + ' failed' : 'all passed'));

await browser.close();

process.exit(failures ? 1 : 0);

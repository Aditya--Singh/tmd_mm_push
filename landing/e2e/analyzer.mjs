// End-to-end check of the hub with the Data Analyzer in its workspace.
//
// The hub signs the person in, opens the Data Analyzer, and the analyzer must be signed
// in too, as the same person, with the role the person holds in the News Feed.
//
// A document is shared, and the analyzer must describe it, draw it and answer a question
// about it.
import { chromium } from 'playwright';
import { writeFileSync } from 'node:fs';

const HUB = process.env.HUB_URL || 'http://127.0.0.1:5174/';
const USER = process.env.E2E_USER || 'analyst';
const PASS = process.env.E2E_PASS || 'Pnb@12345';
const PORT = process.env.E2E_ANALYZER_PORT || '8095';

// The role of the News Feed that the analyzer is given.
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

// A small table to share.
const csv = [
    'branch,balance,opened',
    'Delhi,1000,2023-01-01',
    'Mumbai,2500,2023-02-01',
    'Chennai,800,2023-03-01',
    'Delhi,1200,2023-04-01',
    'Kolkata,640,2023-05-01',
    'Delhi,1100,',
].join('\n');

writeFileSync('/tmp/analyzer-e2e.csv', csv);

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

await frame.locator('body').first().waitFor({ timeout: 25000 });
await page.waitForTimeout(3000);

check('the analyzer opens inside the workspace', true);

const appFrame = page.frames().find((f) => f.url().includes(PORT));
check('the frame of the analyzer is there', appFrame !== undefined);

const hasPasswordField = await frame.locator('input[type="password"]').count();
check('the analyzer shows no sign-in form', hasPasswordField === 0);

// The identity must have travelled with the sign-in.
const who = await appFrame.evaluate(async () => {
    const token = localStorage.getItem('dataanalyzer.token');
    const response = await fetch('/api/documents', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    return response.ok ? await response.json() : { error: response.status, hasToken: !!token };
});

check('the analyzer knows the person', who !== null, JSON.stringify(who));
check(
    'the analyzer signed the person in as the right person',
    who?.username === USER,
    who?.username,
);
check(
    'the analyzer gave the person the role of the news feed',
    who?.role === EXPECTED_ROLE,
    who?.role + ' (expected ' + EXPECTED_ROLE + ')',
);

// The hub's rail must offer the screens of the analyzer.
const sections = (await page.locator('.app-section').allTextContents()).map((s) =>
    s.trim(),
);
check(
    'the hub rail offers the screens of the analyzer',
    sections.length >= 1 && sections[0] === 'Documents',
    JSON.stringify(sections),
);

// A document is shared, and it must be read, described and drawn.
await frame.locator('input[type="file"]').setInputFiles('/tmp/analyzer-e2e.csv');
await page.waitForTimeout(6000);

const heading = await frame.locator('.card__title').allTextContents();
check(
    'the analyzer shows the document',
    heading.some((text) => text.includes('analyzer-e2e')),
    JSON.stringify(heading),
);

const summary = await frame.locator('.card__body p').first().innerText().catch(() => '');
check('the analyzer wrote a summary', summary.length > 0, summary.slice(0, 120));

const pictures = await frame.locator('.plot img').count();
check('the analyzer drew the document', pictures >= 1, pictures + ' pictures');

const columns = await frame.locator('.table tbody tr').count();
check('the analyzer described the columns', columns >= 3, columns + ' columns');

// A question about the document is asked.
await frame.locator('.textarea').fill('Which branch has the highest balance?');
await frame.locator('button', { hasText: 'Ask' }).click();
await page.waitForTimeout(4000);

const answer = await frame.locator('.card__body').last().innerText().catch(() => '');
check('the analyzer answered the question', answer.length > 0, answer.slice(0, 120));

await page.screenshot({ path: '/workspace/analyzer-document.png' });

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

const frameGone = page.frames().find((f) => f.url().includes(PORT)) === undefined;
check('the hub closes the workspace once the app has signed out', frameGone);

const backToLogin = await page.locator('.login-page').count();
check('the hub returns to its sign-in screen', backToLogin === 1);

check('no errors in the browser console', errors.length === 0, errors.join(' | '));

console.log('');
console.log('Checks: ' + (failures ? failures + ' failed' : 'all passed'));

await browser.close();

process.exit(failures ? 1 : 0);

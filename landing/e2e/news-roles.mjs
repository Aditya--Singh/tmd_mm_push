// The news feed has to be shown to every role that can sign in, not only
// to the administrator. This drives the browser through each role.
import { chromium } from 'playwright';

const HUB_URL = process.env.HUB_URL || 'http://localhost:5174/';

//: The role_news column of the account sheet, and whether the news
//: application offers its administrator's screens for it.
const ROLES = [
    { username: 'analyst', password: 'Pnb@12345', isAdmin: false },
    { username: 'approver', password: 'Pnb@12345', isAdmin: false },
    { username: 'gm', password: 'Pnb@12345', isAdmin: false },
    { username: 'aditya', password: 'aditya@news26', isAdmin: false },
    { username: 'admin', password: 'admin@tmd26', isAdmin: true },
];

const results = [];

function check(name, ok, detail = '') {
    results.push({ name, ok });
    console.log(`${ok ? 'PASS' : 'FAIL'} - ${name}${detail ? `  ::  ${detail}` : ''}`);
}

const browser = await chromium.launch({
    ...(process.env.CHROME_BIN ? { executablePath: process.env.CHROME_BIN } : {}),
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
});

for (const role of ROLES) {
    const context = await browser.newContext();
    const page = await context.newPage();

    await page.goto(HUB_URL, { waitUntil: 'networkidle' });
    await page.fill('#username', role.username);
    await page.fill('#password', role.password);
    await page.click('button[type="submit"]');
    await page.waitForSelector('.hub', { timeout: 15000 });

    await page.locator('.app-card', { hasText: 'News Feed' }).click();

    const frame = page.frameLocator('iframe');

    // An administrator opens on the summary and chooses the news from
    // the tabs; everybody else is taken straight to the news.
    await frame
        .locator('.admin-tabs, .news-panel')
        .first()
        .waitFor({ timeout: 25000 });

    const adminTab = frame.locator('.admin-tab', { hasText: 'Latest News' });

    if (await adminTab.count()) {
        await adminTab.first().click();
    }

    let shown = '';

    try {
        await frame.locator('.news-panel').first().waitFor({ timeout: 20000 });
        shown = (await frame.locator('.news-panel h2').first().innerText()).trim();
    } catch {
        shown = 'not shown';
    }

    check(`the news feed is shown to ${role.username}`, shown === 'Latest News', shown);

    // The screens of the administrator follow the role_news column.
    const adminTabs = await frame.locator('.admin-tab').allInnerTexts();

    check(
        `the news feed offers its administrator's screens to ${role.username} only when the role says so`,
        role.isAdmin ? adminTabs.length > 0 : adminTabs.length === 0,
        JSON.stringify(adminTabs),
    );

    await context.close();
}

await browser.close();

const failed = results.filter((result) => !result.ok);

console.log('');
console.log(`Checks: ${results.length}, failed: ${failed.length}`);

process.exit(failed.length ? 1 : 0);

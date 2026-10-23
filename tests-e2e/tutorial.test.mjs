import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';

let server;
let browser;

before(async () => {
  server = await startServer({ configured: true });
  browser = await chromium.launch();
}, { timeout: 120000 });

after(async () => {
  if (browser) await browser.close();
  if (server) await server.stop();
});

test('the tutorial follows the active Arabic display language and current Options components', async () => {
  const { ctx, page, errors } = await loggedInPage(browser);
  try {
    await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
    const update = await page.evaluate(async () => {
      const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
      const response = await fetch(window.dluxEndpoint('update_preferences', {}, '/sys/api/preferences/update/'), {
        method: 'POST',
        credentials: 'same-origin',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrf,
        },
        body: JSON.stringify({ language: 'ar' }),
      });
      return { ok: response.ok, status: response.status, body: await response.text() };
    });
    assert.equal(update.ok, true, `language update failed (${update.status}): ${update.body}`);

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
    assert.equal(await page.getAttribute('html', 'lang'), 'ar');
    assert.equal(await page.getAttribute('html', 'dir'), 'rtl');

    await page.evaluate(() => document.querySelector('[data-dlux-start-tour]').click());
    await page.waitForSelector('.driver-popover-title');

    const tutorial = await page.evaluate(() => ({
      title: document.querySelector('.driver-popover-title')?.textContent.trim(),
      description: document.querySelector('.driver-popover-description')?.textContent.trim(),
      previous: document.querySelector('#tut-prev')?.textContent.trim(),
      next: document.querySelector('#tut-next')?.textContent.trim(),
      skip: document.querySelector('#tut-skip')?.textContent.trim(),
      progress: document.querySelector('#tut-progress')?.textContent.trim(),
      controlsDir: document.querySelector('#tutorial-controls')?.dir,
      textDirection: getComputedStyle(document.querySelector('.driver-popover-title')).direction,
      textAlign: getComputedStyle(document.querySelector('.driver-popover-title')).textAlign,
      controlsInsideViewport: (() => {
        const rect = document.querySelector('#tutorial-controls')?.getBoundingClientRect();
        return !!rect && rect.left >= -1 && rect.right <= window.innerWidth + 1;
      })(),
    }));

    assert.equal(tutorial.title, 'التحكم بالقائمة الجانبية');
    assert.match(tutorial.description, /قائمة/);
    assert.equal(tutorial.previous, 'السابق');
    assert.equal(tutorial.next, 'التالي');
    assert.equal(tutorial.skip, 'إلغاء');
    assert.match(tutorial.progress, /^1 من \d+$/);
    assert.ok(Number(tutorial.progress.split(' ').at(-1)) >= 15, 'the Options tour omitted current components');
    assert.equal(tutorial.controlsDir, 'rtl');
    assert.equal(tutorial.textDirection, 'rtl');
    assert.equal(tutorial.textAlign, 'right');
    assert.equal(tutorial.controlsInsideViewport, true);

    // Options opens as tabs by default, so only the active pane's cards resolve;
    // the tour must still show where the other sections are.
    const total = Number(tutorial.progress.split(' ').at(-1));
    const titles = [tutorial.title];
    for (let i = 1; i < total; i += 1) {
      await page.click('#tut-next');
      await page.waitForFunction((n) => document.querySelector('#tut-progress')?.textContent.trim().startsWith(`${n} `), i + 1);
      titles.push(await page.textContent('.driver-popover-title').then((t) => t.trim()));
    }
    assert.equal(await page.getAttribute('#dluxOptionsGrid', 'data-options-style'), 'tabs');
    assert.ok(titles.includes('أقسام الخيارات'), `the tour skipped the Options tab strip: ${titles.join(' | ')}`);
    assert.deepEqual(errors, []);
  } finally {
    await ctx.close();
  }
});

// Help lives in the user hub, and the hub ignores clicks on the tour's own
// controls, so starting the tour left the hub open over the page for the whole
// tour — covering the Options tab strip the tour points at — and after it
// (found on testbed-dlux, 1.13.1). Starting the tour from the hub closes it.
test('starting the tour from the user hub closes the hub', async () => {
  const { ctx, page } = await loggedInPage(browser);
  try {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
    const card = page.locator('#dlux-user-dropdown-card');
    await page.locator('#dlux-user-dropdown-trigger').click();
    await page.waitForFunction(() => document.getElementById('dlux-user-dropdown-card').classList.contains('show'));
    await card.locator('[data-dlux-start-tour]').click();
    await page.waitForSelector('.driver-popover', { timeout: 5000 });
    assert.equal(await card.evaluate((el) => el.classList.contains('show')), false, 'the hub stayed open over the tour');
    assert.equal(await page.locator('#dlux-user-dropdown-trigger').evaluate((el) => el.classList.contains('active')), false);
  } finally { await ctx.close(); }
});

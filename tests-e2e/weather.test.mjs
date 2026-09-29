import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';

let server, browser;
before(async () => {
  server = await startServer({ weather: true });
  browser = await chromium.launch();
}, { timeout: 120000 });
after(async () => { if (browser) await browser.close(); if (server) await server.stop(); });

async function pageWithWeather(width = 1440) {
  // Fixtures stop all external calls. The Django form, templates and JS are real.
  const ctx = await browser.newContext({ viewport: { width, height: 900 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(10000);
  page.setDefaultNavigationTimeout(15000);
  const errors = [];
  page.on('pageerror', error => errors.push(String(error)));
  let calls = 0;
  await page.route('**/sys/api/weather/?*', route => {
    calls++;
    return route.fulfill({ json: { temperature: 28, feels_like: 30, unit: '°C', icon: 'sun', description: 'clear sky',
      location: 'Tripoli, LY', location_id: '32.88720,13.19130', observed_at: 1790683200, stale: false } });
  });
  await page.goto(`${BASE}/accounts/login/`);
  await page.fill('[name="username"]', 'visual');
  await page.fill('[name="password"]', 'visual-harness-pw');
  await Promise.all([page.waitForURL(url => !url.pathname.includes('/login/')), page.click('button[type="submit"]')]);
  return { ctx, page, errors, calls: () => calls };
}

for (const width of [1440, 390]) {
  test(`floating and dashboard share a request, fit ${width}px, and close on Escape`, async () => {
    const { ctx, page, errors, calls } = await pageWithWeather(width);
    try {
      const before = calls();
      await page.goto(`${BASE}/weather-dashboard/`, { waitUntil: 'networkidle' });
      assert.equal(await page.locator('[data-weather-widget]').count(), 2);
      assert.equal(calls() - before, 1);
      assert.equal(await page.locator('.dlux-weather--card [data-weather-temperature]').innerText(), '28°C');
      const trigger = page.locator('.dlux-weather--floating [data-weather-toggle]');
      await trigger.click();
      assert.equal(await trigger.getAttribute('aria-expanded'), 'true');
      const box = await page.locator('.dlux-weather--floating [data-weather-panel]').boundingBox();
      assert.ok(box.x >= 0 && box.x + box.width <= width, JSON.stringify(box));
      await page.keyboard.press('Escape');
      assert.equal(await trigger.getAttribute('aria-expanded'), 'false');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.screenshot({ path: `tests-e2e/shots/weather-${width}.png`, fullPage: true });
      await page.evaluate(() => { document.documentElement.dir = 'rtl'; });
      const floating = await page.locator('.dlux-weather--floating').boundingBox();
      assert.ok(floating.x < width / 2, 'RTL end floats on the left');
      await trigger.click();
      const rtlBox = await page.locator('.dlux-weather--floating [data-weather-panel]').boundingBox();
      assert.ok(rtlBox.x >= 0 && rtlBox.x + rtlBox.width <= width);
      await page.screenshot({ path: `tests-e2e/shots/weather-${width}-rtl.png`, fullPage: true });
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
}

test('Extra Features uses disabled tooltips, location search and the real save path', async () => {
  const { ctx, page, errors } = await pageWithWeather();
  try {
    await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
    const tile = page.locator('[data-dynamic-modal*="step=17"]').first();
    await tile.click();
    const root = page.locator('[data-weather-settings]');
    await root.waitFor({ state: 'visible' });
    const toggle = root.locator('[name="weather_enabled"]');
    await toggle.uncheck({ force: true });
    assert.equal(await root.locator('[name="weather_api_key"]').isDisabled(), true);
    assert.ok(await root.locator('[data-weather-dependent]').getAttribute('data-dlux-tooltip'));
    await toggle.check({ force: true });
    assert.equal(await root.locator('[name="weather_api_key"]').isDisabled(), false);
    await root.locator('[name="weather_placement"][value="titlebar"]').check({ force: true });
    assert.equal(await root.locator('[name="weather_corner"]').first().isDisabled(), true);
    await page.route('**/sys/api/weather/locations/', route => route.fulfill({ json: {
      locations: [{ id: '32.11670,20.06670', name: 'Benghazi, LY', lat: 32.1167, lon: 20.0667 }],
    } }));
    await root.locator('[data-weather-query]').fill('Benghazi');
    await root.locator('[data-weather-search]').click();
    await root.locator('[data-weather-results] button').click();
    assert.match(await root.locator('[data-weather-chosen]').innerText(), /Benghazi/);
    await root.locator('[name="weather_placement"][value="embed"]').check({ force: true });
    const navigation = page.waitForNavigation({ waitUntil: 'networkidle' });
    const responsePromise = page.waitForResponse(response => response.request().method() === 'POST' && response.url().includes('/sys/modals/'));
    await page.locator('.modal.show button[type="submit"]').last().click();
    const response = await responsePromise;
    assert.equal(response.status(), 200);
    await navigation;
    await page.goto(`${BASE}/weather-dashboard/`, { waitUntil: 'networkidle' });
    assert.equal(await page.locator('[data-weather-widget]').count(), 1, 'embed-only removes floating chrome');
    assert.equal(await page.locator('[data-weather-select] option').count(), 2);
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

test('titlebar and user hub placements open inside the mobile viewport', async () => {
  const { ctx, page, errors } = await pageWithWeather(390);
  try {
    for (const placement of ['titlebar', 'user_hub']) {
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      await page.locator('[data-dynamic-modal*="step=17"]').first().click();
      const root = page.locator('[data-weather-settings]');
      await root.waitFor({ state: 'visible' });
      await root.locator(`[name="weather_placement"][value="${placement}"]`).check({ force: true });
      const navigation = page.waitForNavigation({ waitUntil: 'networkidle' });
      await page.locator('.modal.show button[type="submit"]').last().click();
      await navigation;
      await page.goto(`${BASE}/weather-dashboard/`, { waitUntil: 'networkidle' });
      const host = placement === 'titlebar' ? ':is(.titlebar, .dlux-titlebar-rail)' : '#dlux-user-dropdown-card';
      if (placement === 'titlebar' && await page.locator('.dlux-titlebar-rail [data-weather-toggle]').count()) {
        await page.locator('[data-dlux-titlebar-rail-toggle]').click();
      }
      if (placement === 'user_hub') await page.locator('#dlux-user-dropdown-trigger').click();
      const trigger = page.locator(`${host} [data-weather-toggle]`);
      assert.ok(await trigger.count(), JSON.stringify(await page.locator('[data-weather-widget]').evaluateAll(nodes => nodes.map(node => ({ parent: node.parentElement.className, html: node.outerHTML.slice(0, 350) })))));
      await trigger.click();
      const box = await page.locator(`${host} [data-weather-panel]`).boundingBox();
      assert.ok(box.x >= 0 && box.x + box.width <= 390 && box.y >= 0 && box.y + box.height <= 900, JSON.stringify(box));
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
      await page.screenshot({ path: `tests-e2e/shots/weather-${placement}-390.png`, fullPage: true });
    }
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

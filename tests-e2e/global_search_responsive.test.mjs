// The always-visible titlebar search becomes the standard icon interaction on
// mobile. Its field opens below the titlebar, where it cannot crowd the brand or
// action buttons.
//
// Run: node --test --test-concurrency=1 tests-e2e/global_search_responsive.test.mjs

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';

let server;
let browser;

before(async () => {
  server = await startServer({ configured: true, searchMode: 'always' });
  browser = await chromium.launch();
}, { timeout: 120000 });

after(async () => {
  if (browser) await browser.close();
  if (server) await server.stop();
});

describe('responsive always-visible global search', { concurrency: 1 }, () => {
  test('desktop keeps the configured field in the titlebar', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.setViewportSize({ width: 1024, height: 900 });
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      const layout = await page.evaluate(() => {
        const root = document.querySelector('[data-global-search]');
        const titlebar = document.querySelector('.titlebar').getBoundingClientRect();
        const box = root.querySelector('.dlux-global-search__box').getBoundingClientRect();
        const toggle = root.querySelector('[data-global-search-toggle]');
        return {
          mode: root.dataset.globalSearchMode,
          toggleVisible: toggle.offsetParent !== null,
          boxVisible: box.width > 0 && box.height > 0,
          boxInsideTitlebar: box.top >= titlebar.top && box.bottom <= titlebar.bottom,
        };
      });
      assert.equal(layout.mode, 'always');
      assert.equal(layout.toggleVisible, false);
      assert.equal(layout.boxVisible, true);
      assert.equal(layout.boxInsideTitlebar, true);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('mobile starts as an icon and opens the field below the titlebar', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.setViewportSize({ width: 390, height: 844 });
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      const toggle = page.locator('[data-global-search-toggle]');
      const box = page.locator('.dlux-global-search__box');
      assert.equal(await toggle.isVisible(), true);
      assert.equal(await box.isVisible(), false);

      await toggle.click();
      const layout = await page.evaluate(() => {
        const titlebar = document.querySelector('.titlebar').getBoundingClientRect();
        const boxRect = document.querySelector('.dlux-global-search__box').getBoundingClientRect();
        return {
          visible: boxRect.width > 0 && boxRect.height > 0,
          belowTitlebar: boxRect.top >= titlebar.bottom,
          withinViewport: boxRect.left >= 0 && boxRect.right <= window.innerWidth,
        };
      });
      assert.equal(layout.visible, true);
      assert.equal(layout.belowTitlebar, true);
      assert.equal(layout.withinViewport, true);

      const input = page.locator('[data-global-search-input]');
      const results = page.locator('[data-global-search-results]');
      await input.fill('options');
      await results.waitFor({ state: 'visible' });
      const resultLayout = await page.evaluate(() => {
        const field = document.querySelector('.dlux-global-search__box').getBoundingClientRect();
        const resultsBox = document.querySelector('[data-global-search-results]').getBoundingClientRect();
        return {
          belowField: resultsBox.top >= field.bottom,
          withinViewport: resultsBox.left >= 0 && resultsBox.right <= window.innerWidth,
        };
      });
      assert.equal(resultLayout.belowField, true);
      assert.equal(resultLayout.withinViewport, true);

      await input.fill('');
      await page.mouse.click(10, 300);
      assert.equal(await box.isVisible(), false, 'outside click did not restore the mobile icon');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('resizing an open desktop field to mobile restores the icon', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.setViewportSize({ width: 1024, height: 900 });
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      await page.locator('[data-global-search-input]').focus();
      assert.equal(
        await page.locator('[data-global-search]').evaluate((root) => root.classList.contains('dlux-global-search--open')),
        true,
      );

      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(50);
      assert.equal(await page.locator('[data-global-search-toggle]').isVisible(), true);
      assert.equal(await page.locator('.dlux-global-search__box').isVisible(), false);

      await page.setViewportSize({ width: 1024, height: 900 });
      assert.equal(await page.locator('[data-global-search-toggle]').isVisible(), false);
      assert.equal(await page.locator('.dlux-global-search__box').isVisible(), true);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

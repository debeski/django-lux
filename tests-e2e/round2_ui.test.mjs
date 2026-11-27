// Break-it round 2 UI findings that only show in a browser.
//
// R2-091: in a zero-width collapsed sidebar the toolbar still laid out, so the
// theme toggle overhung the viewport edge (RTL at 1024/768/375, LTR at <=768)
// and stayed keyboard-focusable. R2-110: modal close buttons were labelled in
// English on Arabic pages.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, BASE, chromium } from './server.mjs';

async function setPreferences(page, prefs) {
  await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
  const ok = await page.evaluate(async (body) => {
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const response = await fetch(window.dluxEndpoint('update_preferences', {}, '/sys/api/preferences/update/'), {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(body),
    });
    return response.ok;
  }, prefs);
  assert.equal(ok, true);
}

describe('round 2 UI', { concurrency: 1 }, () => {
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

  for (const language of ['en', 'ar']) {
    test(`the theme toggle never overhangs the viewport (${language})`, async () => {
      const { ctx, page, errors } = await loggedInPage(browser);
      try {
        await setPreferences(page, { language });
        for (const width of [1280, 1024, 768, 375]) {
          await page.setViewportSize({ width, height: 800 });
          await page.goto(`${BASE}/sys/users/`, { waitUntil: 'networkidle' });
          const state = await page.evaluate(() => {
            const toggle = document.querySelector('.current-theme-indicator');
            const rect = toggle.getBoundingClientRect();
            const shown = rect.width > 0 && getComputedStyle(toggle).display !== 'none';
            return {
              shown,
              inside: !shown || (rect.left >= 0 && rect.right <= window.innerWidth),
              focusable: shown && toggle.tabIndex >= 0,
            };
          });
          assert.equal(state.inside, true, `${language} ${width}: ${JSON.stringify(state)}`);
          if (!state.shown) assert.equal(state.focusable, false);
        }
        assert.deepEqual(errors, []);
      } finally { await ctx.close(); }
    });
  }

  test('modal close buttons are labelled in Arabic', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await setPreferences(page, { language: 'ar' });
      await page.goto(`${BASE}/sys/users/`, { waitUntil: 'networkidle' });
      const labels = await page.$$eval('.btn-close', (buttons) => buttons.map((button) => button.getAttribute('aria-label')));
      assert.ok(labels.length > 0);
      assert.deepEqual(labels.filter((label) => label === 'Close'), []);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

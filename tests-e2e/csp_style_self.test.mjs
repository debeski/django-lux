// DjangoLux under `style-src 'self'` (ZAP 10055).
//
// settings.py sends `style-src 'self'`: no 'unsafe-inline', no nonce. That
// blocks <style> blocks, style="" attributes and markup with style= handed to
// innerHTML. The CSSOM (el.style.x, setProperty) and same-origin stylesheets
// stay allowed. Every staff screen here, in both directions and in the dark
// theme, must load and work without one CSP violation.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, BASE, chromium } from './server.mjs';
import { ROUTES } from './routes.mjs';

const WATCH = () => {
  window.__cspViolations = [];
  document.addEventListener('securitypolicyviolation', (event) => {
    window.__cspViolations.push(`${event.effectiveDirective} ${event.blockedURI} ${event.sample || ''}`.trim());
  });
};
const violations = (page) => page.evaluate(() => window.__cspViolations || []);
const PAGES = [...ROUTES.filter((route) => route.phase === 'main').map((route) => route.path),
  '/sys/options/?tab=appearance', '/sys/sections/'];

async function setPreferences(page, prefs) {
  const result = await page.evaluate(async (body) => {
    const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
    const response = await fetch(window.dluxEndpoint('update_preferences', {}, '/sys/api/preferences/update/'), {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
      body: JSON.stringify(body),
    });
    return { ok: response.ok, status: response.status };
  }, prefs);
  assert.equal(result.ok, true, `preferences update failed (${result.status})`);
}

describe('style-src self', { concurrency: 1 }, () => {
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

  test('the policy allows no inline style', async () => {
    const response = await fetch(`${BASE}/accounts/login/`);
    const policy = response.headers.get('content-security-policy') || '';
    const styleSrc = policy.split(';').map((part) => part.trim()).find((part) => part.startsWith('style-src')) || '';
    assert.equal(styleSrc, "style-src 'self'");
  });

  test('the sign-in page loads its fonts without inline style', async () => {
    const ctx = await browser.newContext();
    await ctx.addInitScript(WATCH);
    const page = await ctx.newPage();
    try {
      await page.goto(`${BASE}/accounts/login/`, { waitUntil: 'networkidle' });
      assert.deepEqual(await violations(page), []);
      const fonts = await page.evaluate(() => ({
        sheet: !!document.getElementById('dlux-page-styles')?.sheet?.cssRules.length,
        main: getComputedStyle(document.documentElement).getPropertyValue('--dlux-main-font').trim(),
        fallback: getComputedStyle(document.documentElement).getPropertyValue('--dlux-font-fallback').trim(),
        body: getComputedStyle(document.body).fontFamily,
      }));
      assert.equal(fonts.sheet, true);
      assert.match(fonts.main, /^'?[A-Za-z]/);
      assert.match(fonts.fallback, /^'?[A-Za-z]/);
      assert.ok(fonts.body.includes(fonts.main.split(',')[0].replace(/'/g, '').trim()), JSON.stringify(fonts));
    } finally { await ctx.close(); }
  });

  for (const variant of [
    { name: 'light LTR', prefs: { theme: 'light', language: 'en' } },
    { name: 'light RTL', prefs: { theme: 'light', language: 'ar' } },
    { name: 'dark LTR', prefs: { theme: 'dark', language: 'en' } },
    { name: 'dark RTL', prefs: { theme: 'dark', language: 'ar' } },
  ]) {
    test(`every staff screen loads without a violation (${variant.name})`, { timeout: 180000 }, async () => {
      const { ctx, page, errors } = await loggedInPage(browser);
      await ctx.addInitScript(WATCH);
      try {
        await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
        await setPreferences(page, variant.prefs);
        for (const route of PAGES) {
          await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle' });
          assert.deepEqual(await violations(page), [], `${variant.name} ${route}`);
        }
        assert.deepEqual(errors, []);
      } finally { await ctx.close(); }
    });
  }

  test('a modal shows its loading skeleton and form without inline style', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    await ctx.addInitScript(WATCH);
    try {
      await page.goto(`${BASE}/sys/users/`, { waitUntil: 'networkidle' });
      await page.route('**/sys/modals/users/**', async (route) => {
        await new Promise((resolve) => setTimeout(resolve, 600));
        await route.continue();
      });
      await page.evaluate(() => document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
        detail: { data: { url: '/sys/modals/users/', title: 'User' } },
      })));
      const skeleton = await page.waitForSelector('.dynamic-modal-skeleton', { timeout: 5000 });
      const size = await skeleton.evaluate((el) => ({ width: el.style.width, height: el.style.height, bg: getComputedStyle(el).backgroundColor }));
      assert.ok(size.width && size.height, JSON.stringify(size));
      assert.notEqual(size.bg, 'rgba(0, 0, 0, 0)');
      await page.waitForSelector('#universalDynamicModalBody form', { timeout: 10000 });
      await page.waitForLoadState('networkidle');
      assert.deepEqual(await violations(page), []);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the guided tour styles its popover from the stylesheet', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    await ctx.addInitScript(WATCH);
    try {
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      await page.evaluate(() => document.querySelector('[data-dlux-start-tour]').click());
      await page.waitForSelector('.driver-popover-title');
      const look = await page.evaluate(() => ({
        controls: getComputedStyle(document.getElementById('tutorial-controls')).position,
        button: getComputedStyle(document.querySelector('.tut-btn')).borderRadius,
        popover: getComputedStyle(document.querySelector('.driver-popover')).maxWidth,
      }));
      assert.equal(look.controls, 'fixed');
      assert.equal(look.button, '50px');
      assert.equal(look.popover, '400px');
      assert.deepEqual(await violations(page), []);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

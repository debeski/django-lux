// Pages load their strings table as a cached script, in both languages.
//
// base.html used to embed the whole table on every page; it now names
// /sys/api/strings/<lang>.<version>.js just before base_head.js. Scripts read
// window.DLUX_STRINGS synchronously, so this drives a real browser to show the
// table is in place before they run, for a visitor and for a signed-in user in
// English and Arabic, with no console errors.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';
import { VIEWPORT } from './routes.mjs';

const EXPECTED = { en: 'Assisted entry', ar: 'إدخال مساعَد' };
const SCRIPT = /\/sys\/api\/strings\/(\w+)\.[0-9a-f]{16}\.js$/;

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

async function switchLanguage(page, lang) {
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle' }),
    page.evaluate((code) => window.setLanguage(code), lang),
  ]);
}

/** What the page's scripts see, and which strings script it loaded. */
async function inspect(page) {
  return page.evaluate(() => ({
    lang: document.documentElement.lang,
    // The compatibility element for scripts that parse the old block.
    legacyKeys: (() => {
      try { return Object.keys(JSON.parse(document.getElementById('dlux-strings-data').textContent)).length; } catch { return -1; }
    })(),
    script: [...document.scripts].map((s) => s.src).find((src) => src.includes('/sys/api/strings/')) || '',
    keys: Object.keys(window.DLUX_STRINGS || {}).length,
    legend: window.dluxString ? window.dluxString('assist_bar_legend') : null,
  }));
}

function assertStrings(state, lang) {
  assert.equal(state.lang, lang);
  assert.equal(SCRIPT.exec(new URL(state.script || 'http://x/').pathname)?.[1], lang);
  assert.ok(state.keys > 1000, `the whole table is loaded (${state.keys} keys)`);
  assert.equal(state.legend, EXPECTED[lang]);
  assert.equal(state.legacyKeys, state.keys, 'the old #dlux-strings-data readers still get the table');
}

describe('strings script', { concurrency: 1 }, () => {
  // The preferences API that switches language needs a signed-in user, so a
  // visitor is shown in the default language here; the Python suite renders the
  // sign-in page with an Arabic session.
  test('a visitor on the sign-in page gets strings', async () => {
    const ctx = await browser.newContext({ viewport: VIEWPORT, locale: 'en-US', timezoneId: 'UTC' });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(`THROWN: ${e}`));
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
    try {
      const response = await page.goto(`${BASE}/accounts/login/`, { waitUntil: 'networkidle' });
      assert.equal(response.status(), 200);
      assert.doesNotMatch(await response.text(), /id="dlux-strings-data"/, 'the page does not embed the table');
      assertStrings(await inspect(page), 'en');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a signed-in user gets strings in both languages, cached for good', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    const served = [];
    page.on('response', (r) => { if (SCRIPT.test(new URL(r.url()).pathname)) served.push(r); });
    try {
      await page.goto(`${BASE}/sys/users/`, { waitUntil: 'networkidle' });
      assertStrings(await inspect(page), 'en');
      await switchLanguage(page, 'ar');
      assertStrings(await inspect(page), 'ar');
      const arabic = served.find((r) => SCRIPT.exec(new URL(r.url()).pathname)[1] === 'ar');
      assert.match(arabic.headers()['cache-control'], /immutable/);
      await page.goto(`${BASE}/accounts/profile/`, { waitUntil: 'networkidle' });
      assertStrings(await inspect(page), 'ar');
      await switchLanguage(page, 'en');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

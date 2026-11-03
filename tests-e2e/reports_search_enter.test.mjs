// General Reports: Enter in a builder field.
//
// The header's Print and Export buttons are submit buttons of the builder form
// (`form="general-report-form"`) and come before it in the document, so the
// browser's implicit submission pressed Print: Enter in the search opened the
// print view in a new tab instead of filtering. Enter in the search now applies
// the builder; Enter in a model or operation filter only filters.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
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

describe('reports builder: Enter', () => {
  test('Enter in the search filters the page and opens no print view', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.goto(`${BASE}/sys/reports/`, { waitUntil: 'networkidle' });
      const opened = [];
      ctx.on('page', (p) => opened.push(p.url()));

      await page.fill('#reports-search', 'admin');
      await Promise.all([
        page.waitForURL((url) => url.searchParams.get('q') === 'admin', { timeout: 10000 }),
        page.press('#reports-search', 'Enter'),
      ]);
      await page.waitForLoadState('networkidle');

      const url = new URL(page.url());
      assert.equal(url.pathname, '/sys/reports/');
      assert.deepEqual(opened, []);
      assert.equal(await page.inputValue('#reports-search'), 'admin');
      assert.deepEqual(errors, []);
    } finally {
      await ctx.close();
    }
  });

  test('Enter in a model or operation filter stays on the page', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.goto(`${BASE}/sys/reports/`, { waitUntil: 'networkidle' });
      const filter = page.locator('[data-report-choice-search]').first();
      assert.ok(await filter.count(), 'the builder renders a choice filter');
      const before = page.url();
      const opened = [];
      ctx.on('page', (p) => opened.push(p.url()));
      let navigated = false;
      page.on('framenavigated', (frame) => { if (frame === page.mainFrame()) navigated = true; });

      await filter.fill('zz');
      await filter.press('Enter');
      await page.waitForTimeout(1000);

      assert.equal(navigated, false);
      assert.deepEqual(opened, []);
      assert.equal(page.url(), before);
      assert.deepEqual(errors, []);
    } finally {
      await ctx.close();
    }
  });
});

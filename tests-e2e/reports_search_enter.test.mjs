// General Reports: Enter in a builder field.
//
// The header's Print and Export buttons are submit buttons of the builder form
// (`form="general-report-form"`) and come before it in the document, so the
// browser's implicit submission pressed Print: Enter in the search, on the
// period or on a checkbox opened the print view instead of filtering. Enter in
// any of them now applies the builder; Enter in a model or operation filter only
// filters.
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

  for (const [name, selector] of [
    ['the period', '#reports-window'],
    ['a model checkbox', 'input[name="models"]'],
  ]) {
    test(`Enter on ${name} applies the builder and opens no print view`, async () => {
      const { ctx, page, errors } = await loggedInPage(browser);
      try {
        await page.goto(`${BASE}/sys/reports/`, { waitUntil: 'networkidle' });
        const field = page.locator(selector).first();
        assert.ok(await field.count(), `the builder renders ${name}`);
        const checked = selector.startsWith('input') ? await field.isChecked() : null;
        const opened = [];
        ctx.on('page', (p) => opened.push(p.url()));

        await field.focus();
        await Promise.all([
          page.waitForURL((url) => url.searchParams.get('builder') === '1', { timeout: 10000 }),
          page.keyboard.press('Enter'),
        ]);
        await page.waitForLoadState('networkidle');

        assert.equal(new URL(page.url()).pathname, '/sys/reports/');
        assert.deepEqual(opened, []);
        if (checked !== null) assert.equal(await page.locator(selector).first().isChecked(), checked);
        assert.deepEqual(errors, []);
      } finally {
        await ctx.close();
      }
    });
  }

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

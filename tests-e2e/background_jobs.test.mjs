// Long requests handed to the task worker: Export entries and Reset data.
//
// The harness runs no worker, so the server takes the synchronous path; the
// worker path is driven by answering the start and status requests the way a
// live worker's job would.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';
import { CREDENTIALS } from './routes.mjs';

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

const exportButton = '[data-dlux-job-start-url]';

describe('Export entries', () => {
  test('without a worker it downloads the workbook from the synchronous URL', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.goto(`${BASE}/sys/reports/`, { waitUntil: 'networkidle' });
      const [download] = await Promise.all([
        page.waitForEvent('download', { timeout: 20000 }),
        page.locator(exportButton).first().click(),
      ]);
      assert.match(download.suggestedFilename(), /^dlux-entries-.*\.xlsx$/);
      assert.equal(await page.locator(exportButton).first().isDisabled(), false);
      assert.deepEqual(errors, []);
    } finally {
      await ctx.close();
    }
  });

  test('with a worker it shows the job progress, then downloads its file', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.goto(`${BASE}/sys/reports/`, { waitUntil: 'networkidle' });
      let started = null;
      await page.route('**/sys/reports/export/start/', (route) => {
        started = new URLSearchParams(route.request().postData() || '');
        return route.fulfill({ json: { ok: true, async: true, token: 'e2e', status_url: '/sys/api/jobs/e2e/' } });
      });
      let polls = 0;
      await page.route('**/sys/api/jobs/e2e/', (route) => {
        polls += 1;
        return route.fulfill({ json: polls < 2
          ? { status: 'running', progress_percent: 40, progress_message: 'Exporting papers...' }
          : { status: 'completed', progress_percent: 100, download_url: '/sys/reports/export.xlsx?window=all' } });
      });
      const button = page.locator(exportButton).first();
      const downloadPromise = page.waitForEvent('download', { timeout: 20000 });
      await button.click();
      await page.waitForFunction(
        (selector) => (document.querySelector(selector).textContent || '').includes('Exporting papers... 40%'),
        exportButton,
      );
      assert.equal(await button.isDisabled(), true);
      const download = await downloadPromise;
      assert.match(download.suggestedFilename(), /^dlux-entries-all-.*\.xlsx$/);
      assert.ok(started && started.get('window'), 'the builder form is posted to the start URL');
      await page.waitForFunction((selector) => !document.querySelector(selector).disabled, exportButton);
      assert.deepEqual(errors, []);
    } finally {
      await ctx.close();
    }
  });
});

describe('Reset data', () => {
  test('a queued reset reports its progress and outcome', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      await page.evaluate(() => document.querySelector('[data-data-reset-open]').click());
      await page.locator('[data-dlux-confirm-modal].show [data-dlux-confirm-password]').fill(CREDENTIALS.password);
      await page.locator('[data-dlux-confirm-modal].show [data-dlux-confirm-submit]').click();
      const modal = page.locator('[data-data-reset-modal].show');
      await modal.waitFor({ state: 'visible' });
      const choice = modal.locator('input[type="checkbox"][data-model]:not([disabled])').first();
      await choice.check({ force: true });

      let executed = null;
      await page.route('**/sys/admin/data-reset/execute/', (route) => {
        executed = route.request().postData() || '';
        return route.fulfill({ status: 202, json: { status: 'queued', job: { ok: true, async: true, token: 'reset', status_url: '/sys/api/jobs/reset/' } } });
      });
      let polls = 0;
      await page.route('**/sys/api/jobs/reset/', (route) => {
        polls += 1;
        return route.fulfill({ json: polls < 2
          ? { status: 'running', progress_percent: 50, progress_message: 'Clearing papers...' }
          : { status: 'completed', progress_percent: 100, result: { status: 'success', message: 'Data reset complete: 3 row(s) cleared.' } } });
      });
      await modal.locator('[data-data-reset-execute]').click();
      const result = modal.locator('[data-data-reset-result]');
      await page.waitForFunction(() => (document.querySelector('[data-data-reset-result]').textContent || '').includes('Clearing papers... 50%'));
      await page.waitForFunction(() => (document.querySelector('[data-data-reset-result]').textContent || '').includes('Data reset complete: 3 row(s) cleared.'));
      assert.match(await result.getAttribute('class'), /alert-success/);
      assert.ok(executed && executed.includes('current_password='), 'the password is sent with the reset');
      assert.deepEqual(errors, []);
    } finally {
      await ctx.close();
    }
  });
});

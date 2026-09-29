// A project settings tile asks before discarding unsaved edits.
//
// The tile template carried the guard marker and the Python tests checked it,
// yet closing a dirty tile discarded silently: the dynamic modal inserts the
// tile's <form> as the node itself, and the guard only looked *below* each
// inserted node. Only a browser shows the difference, so this drives it.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';

const TILE = '[data-dynamic-modal$="/app-settings/e2e.project/"]';
const FORM = '.modal.show form.dlux-app-settings-form';

let server;
let browser;

before(async () => {
  server = await startServer({ configured: true, projectSettings: true });
  browser = await chromium.launch();
}, { timeout: 120000 });

after(async () => {
  if (browser) await browser.close();
  if (server) await server.stop();
});

async function openTile(page) {
  await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
  await page.click(TILE);
  await page.waitForSelector(FORM, { timeout: 10000 });
  // The guard snapshots the form two animation frames after it lands.
  await page.waitForFunction((sel) => document.querySelector(sel)?.dataset.dluxUnsavedBaseline !== undefined,
    FORM, { timeout: 5000 });
  // Bootstrap ignores a close while the modal is still animating open.
  await page.waitForTimeout(600);
}

describe('project settings tile unsaved guard', { concurrency: 1 }, () => {
  test('closing a tile with unsaved edits prompts', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await openTile(page);
      await page.fill(`${FORM} input[name="limit"]`, '17');
      await page.keyboard.press('Escape');
      await page.waitForSelector('#dluxUnsavedModal.show', { timeout: 5000 });
      assert.equal(await page.isVisible(FORM), true, 'the tile stays open behind the prompt');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('closing an untouched tile does not prompt', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await openTile(page);
      await page.keyboard.press('Escape');
      await page.waitForSelector('.modal.show form.dlux-app-settings-form', { state: 'hidden', timeout: 5000 });
      assert.equal(await page.isVisible('#dluxUnsavedModal.show'), false);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

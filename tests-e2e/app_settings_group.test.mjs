// A grouped project settings tile: several register_app_settings() namespaces
// under one Options tile, edited in one modal and saved in one write.
//
// The Python tests prove the view validates and saves every section. This
// drives the modal the way an administrator does: the tile opens it, a change
// in the second section survives the save, and closing a dirty group prompts.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';

const TILE = '[data-dynamic-modal$="/app-settings-group/e2e.group/"]';
const FORM = '.modal.show .dlux-app-settings-group-form';
const BETA = 'app__e2e_beta-limit';

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

async function openGroup(page) {
  await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
  await page.click(TILE);
  await page.waitForSelector(FORM, { timeout: 10000 });
  await page.waitForTimeout(400);
}

describe('grouped project settings tile', { concurrency: 1 }, () => {
  test('one tile for the group, and its modal holds every section', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      assert.equal(await page.locator(TILE).count(), 1, 'the group is one tile');
      assert.equal(await page.locator('[data-dynamic-modal$="/app-settings/e2e.alpha/"]').count(), 0,
        'a grouped namespace has no tile of its own');
      await openGroup(page);
      const sections = await page.$$eval(`${FORM} [data-dlux-app-settings-section] h6`, (hs) => hs.map((h) => h.textContent.trim()));
      assert.deepEqual(sections, ['Section Alpha', 'Section Beta']);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a change in one section survives the save', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await openGroup(page);
      await page.fill(`input[name="${BETA}"]`, '42');
      await Promise.all([
        page.waitForEvent('load', { timeout: 15000 }),
        page.click('.modal.show button[type="submit"]'),
      ]);
      await openGroup(page);
      assert.equal(await page.inputValue(`input[name="${BETA}"]`), '42');
      assert.equal(await page.inputValue('input[name="app__e2e_alpha-limit"]'), '1', 'the other section kept its value');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('closing a group with unsaved edits prompts', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await openGroup(page);
      await page.fill(`input[name="${BETA}"]`, '7');
      await page.keyboard.press('Escape');
      await page.waitForSelector('#dluxUnsavedModal.show', { timeout: 5000 });
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

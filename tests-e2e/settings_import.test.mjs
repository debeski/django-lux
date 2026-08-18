// Drives the Options-page config import in a real browser.
//
// Written after shipping it broken: the review rendered *inside the options
// card* instead of a modal, which distorted the page and made it unusable. Two
// causes, both from guessing at an API instead of reading it —
//
//   1. there is no `window.dluxOpenDynamicModal`. The dynamic modal is
//      URL-driven: `data-dynamic-modal="<url>"`, or a `dlux:dynamic_modal:open`
//      event carrying `detail.data.url`. Handing it raw HTML is not part of the
//      protocol, so the code fell through to an inline fallback.
//   2. the modal fetches that URL and parses the response as JSON, injecting
//      `data.html`. Returning an HTML document fails with a JSON parse error.
//
// Both are invisible to the view tests, which never load a page. Hence this.
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

const CONFIG = JSON.stringify({
  format: 'django-lux.system-settings',
  dlux_version: '1.8.0',
  settings: { home_url: '/imported/', footer_text: 'imported footer' },
});

async function optionsPage() {
  const { ctx, page, errors } = await loggedInPage(browser);
  await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
  return { ctx, page, errors };
}

async function uploadConfig(page, body = CONFIG) {
  await page.setInputFiles('[data-settings-import-file]', {
    name: 'config.json', mimeType: 'application/json', buffer: Buffer.from(body),
  });
  await page.waitForSelector('[data-settings-import-review]', { timeout: 10000 });
}

describe('options config import', { concurrency: 1 }, () => {
  test('the tile is present and creates its file input', async () => {
    const { ctx, page, errors } = await optionsPage();
    try {
      assert.ok(await page.$('[data-settings-import-open]'), 'no import tile');
      assert.ok(await page.$('[data-settings-import-file]'), 'no file input was created');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the review opens in the dynamic modal, not inside the options card', async () => {
    // The actual reported bug: it rendered into the card and wrecked the layout.
    const { ctx, page, errors } = await optionsPage();
    try {
      await uploadConfig(page);
      const where = await page.evaluate(() => {
        const review = document.querySelector('[data-settings-import-review]');
        const modal = review.closest('.modal');
        return {
          insideModal: !!modal,
          modalVisible: modal ? modal.classList.contains('show') : false,
          insideOptionsCard: !!review.closest('.dlux-options-card'),
        };
      });
      assert.equal(where.insideModal, true, 'the review is not inside a modal');
      assert.equal(where.modalVisible, true, 'the modal did not open');
      assert.equal(where.insideOptionsCard, false, 'the review leaked into the options card');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('every change starts unticked', async () => {
    const { ctx, page, errors } = await optionsPage();
    try {
      await uploadConfig(page);
      const boxes = await page.$$eval('[data-settings-import-check]',
        (els) => els.map((e) => e.checked));
      assert.ok(boxes.length >= 2, `expected the two changes, saw ${boxes.length}`);
      assert.deepEqual(
        boxes.filter(Boolean), [],
        'on a live system the safe default is to keep the current value',
      );
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a group master ticks everything under it and goes indeterminate on a partial', async () => {
    // Mirrors the permissions widget, which is the selection pattern this app
    // already uses — the review reuses its markup and stylesheet rather than
    // introducing a second one.
    const { ctx, page, errors } = await optionsPage();
    try {
      await uploadConfig(page);
      const card = '[data-settings-import-group]';
      const master = `${card} .app-master-checkbox`;

      await page.click(master);
      const afterAll = await page.$$eval('[data-settings-import-check]',
        (els) => els.filter((e) => e.checked).length);
      assert.ok(afterAll >= 2, 'the master ticked nothing');

      // Untick one child: the master must fall to indeterminate, not to off.
      await page.click('[data-settings-import-check]');
      const state = await page.evaluate((sel) => {
        const m = document.querySelector(sel);
        return { checked: m.checked, indeterminate: m.indeterminate };
      }, master);
      assert.equal(state.checked, false);
      assert.equal(state.indeterminate, true, 'a partial selection must show as indeterminate');

      // Clicking an indeterminate checkbox sets it to checked in every browser,
      // so it selects the rest rather than clearing — same as the permissions
      // widget, which is the behaviour being mirrored. Clearing takes a second
      // click, from the now-checked state.
      await page.click(master);
      const afterResolve = await page.$$eval('[data-settings-import-check]',
        (els) => els.filter((e) => e.checked).length);
      assert.equal(afterResolve, afterAll, 'an indeterminate master should resolve to all-selected');

      await page.click(master);
      const afterOff = await page.$$eval('[data-settings-import-check]',
        (els) => els.filter((e) => e.checked).length);
      assert.equal(afterOff, 0, 'clicking a checked master clears the card');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the review uses the permissions-widget markup', async () => {
    const { ctx, page, errors } = await optionsPage();
    try {
      await uploadConfig(page);
      const shape = await page.evaluate(() => ({
        cards: document.querySelectorAll('[data-settings-import-review] .permissions-card').length,
        headers: document.querySelectorAll('[data-settings-import-review] .permissions-card-header').length,
        masters: document.querySelectorAll('[data-settings-import-review] .app-master-checkbox').length,
        collapsedByDefault: [...document.querySelectorAll('[data-settings-import-review] .collapse')]
          .every((c) => !c.classList.contains('show')),
      }));
      assert.ok(shape.cards >= 1, 'no permissions-card was rendered');
      assert.equal(shape.headers, shape.cards);
      assert.equal(shape.masters, shape.cards);
      assert.equal(shape.collapsedByDefault, true, 'groups should start collapsed');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('applying one ticked change moves only that setting', async () => {
    const { ctx, page, errors } = await optionsPage();
    try {
      await uploadConfig(page);
      // Cards start collapsed; open the one holding the change before ticking.
      await page.click('[data-settings-import-group] .permissions-card-header');
      await page.waitForTimeout(500);
      await page.click('[data-settings-import-check][value="home_url"]');
      await Promise.all([
        page.waitForLoadState('networkidle'),
        page.click('[data-settings-import-apply]'),
      ]);
      await page.waitForTimeout(500);

      // The page reloads on success; read the applied value back off the form.
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      const applied = await page.evaluate(async () => {
        const r = await fetch('/sys/settings/export/', { credentials: 'same-origin' });
        return (await r.json()).settings;
      });
      assert.equal(applied.home_url, '/imported/', 'the ticked change was not applied');
      assert.notEqual(
        applied.footer_text, 'imported footer',
        'an unticked change rode along with the apply',
      );
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a file that is not JSON is refused without opening a review', async () => {
    const { ctx, page, errors } = await optionsPage();
    try {
      await page.setInputFiles('[data-settings-import-file]', {
        name: 'config.json', mimeType: 'application/json', buffer: Buffer.from('not json'),
      });
      await page.waitForTimeout(900);
      assert.equal(
        await page.$('[data-settings-import-review]'), null,
        'a malformed file should not produce a review',
      );
    } finally { await ctx.close(); }
  });
});

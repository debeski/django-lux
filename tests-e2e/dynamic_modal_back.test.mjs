// The dynamic modal's Back button must not reload the view it is already on.
//
// Back exists for the section-manager flow: the modal opens on a record list,
// you click into one record, Back returns you to the list. It did that by
// reloading `currentBaseUrl` -- the URL the modal was *opened* with.
//
// A modal-first project never opens the list. Its row actions fire
// dlux:dynamic_modal:open with one record's URL, so currentBaseUrl IS the
// detail view, and Back re-fetched the same page: the button visibly did
// nothing. With no list behind it, Back has to close the modal instead.
//
// Driven against the shipped helper with a stubbed fetch, because the bug is in
// which URL the handler chooses -- something no server-side test can observe.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from './server.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.join(HERE, '..', 'dlux', 'static');
const PORT = 8732;
const BASE = `http://localhost:${PORT}`;

// The shell the helper binds to, matching dlux's modal include.
const PAGE = `<!doctype html><html><head><meta charset="utf-8"></head><body>
<div class="modal fade" id="universalDynamicModal" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content">
    <div class="modal-header"><span id="dynamicModalTitleText"></span></div>
    <div class="modal-body" id="universalDynamicModalBody"></div>
    <div class="modal-footer" id="universalDynamicModalFooter"></div>
  </div></div>
</div>
<script src="/bootstrap/bootstrap.bundle.min.js"></script>
<script>
  window.__fetched = [];
  window.fetch = function (url, options) {
    window.__fetched.push(String(url));
    if (options && options.method === 'POST') {
      if (String(url).includes('/rename/')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ success: true, title: 'Renamed image' }),
        });
      }
      const payload = JSON.stringify({ success: true, reload_current: true });
      return Promise.resolve({ ok: true, text: () => Promise.resolve(payload) });
    }
    if (String(url).includes('/sys/assets/')) {
      const fonts = String(url).includes('asset_tab=fonts');
      const html = fonts
        ? '<div data-dlux-modal-nav><a href="/sys/assets/?asset_tab=images">images</a></div><form action="/sys/assets/?asset_tab=fonts"><input name="csrfmiddlewaretoken" value="token"><button type="submit" data-font-submit>upload font</button></form><div data-font-list></div>'
        : '<div data-dlux-modal-nav><a href="/sys/assets/?asset_tab=fonts">fonts</a></div><form action="/sys/assets/?asset_tab=images"><input name="csrfmiddlewaretoken" value="token"><input type="file" name="file" multiple data-managed-image-input><div data-dlux-modal-footer><button type="submit" data-image-submit data-managed-image-upload-trigger>upload images</button></div></form><div data-image-grid><div class="dlux-managed-asset-name"><button type="button" data-managed-image-title data-rename-url="/sys/assets/rename/7/">Original image</button><input value="Original image" data-managed-image-title-input hidden></div></div>';
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ html }) });
    }
    const isList = String(url).endsWith('/manage/');
    const html = isList
      ? '<div><button class="dynamic-edit-btn" data-pk="5">row</button></div>'
      : '<div><button class="dynamic-back-btn">back</button></div>';
    return Promise.resolve({
      ok: true,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ html }),
      text: () => Promise.resolve(html),
    });
  };
</script>
<script src="/dlux/helpers/dynamic_modal/js/main.js"></script>
<script src="/dlux/assets/js/main.js"></script>
</body></html>`;

let server;
let browser;
let page;

before(async () => {
  server = http.createServer((req, res) => {
    const url = req.url.split('?')[0];
    if (url === '/' || url === '/page.html') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      return res.end(PAGE);
    }
    const file = path.join(STATIC, url);
    if (!file.startsWith(STATIC) || !fs.existsSync(file)) {
      res.writeHead(404);
      return res.end();
    }
    res.writeHead(200, { 'Content-Type': 'text/javascript' });
    res.end(fs.readFileSync(file));
  });
  await new Promise((resolve) => server.listen(PORT, resolve));
  browser = await chromium.launch();
  page = await browser.newPage();
}, { timeout: 120000 });

after(async () => {
  if (browser) await browser.close();
  if (server) await new Promise((resolve) => server.close(resolve));
});

const openModal = (url) => page.evaluate((target) => {
  window.__fetched = [];
  document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
    detail: { data: { url: target, title: 'T' } },
  }));
}, url);

const modalVisible = () => page.evaluate(
  () => document.getElementById('universalDynamicModal').classList.contains('show'));

const clickIn = async (selector) => {
  await page.waitForSelector(`#universalDynamicModalBody ${selector}`);
  await page.click(`#universalDynamicModalBody ${selector}`);
};

describe('dynamic modal back button', () => {
  test('closes the modal when the record was opened directly', async () => {
    await page.goto(`${BASE}/page.html`);
    await openModal('/app-modals/storage/Asset/5/?action=view');
    await page.waitForFunction(
      () => document.getElementById('universalDynamicModal').classList.contains('show'));

    await clickIn('.dynamic-back-btn');

    await page.waitForFunction(
      () => !document.getElementById('universalDynamicModal').classList.contains('show'),
      { timeout: 4000 });
    assert.equal(await modalVisible(), false, 'modal should be closed');
  });

  test('still returns to the list when one is behind it', async () => {
    await page.goto(`${BASE}/page.html`);
    await openModal('/sys/sections/manage/');
    await clickIn('.dynamic-edit-btn');
    await clickIn('.dynamic-back-btn');

    await page.waitForFunction(
      () => window.__fetched.filter(u => u.endsWith('/manage/')).length >= 2,
      { timeout: 4000 });

    assert.equal(await modalVisible(), true, 'modal should stay open on the list');
    const fetched = await page.evaluate(() => window.__fetched);
    assert.ok(fetched.at(-1).endsWith('/manage/'), `last fetch was ${fetched.at(-1)}`);
  });
});

describe('dynamic modal internal navigation', () => {
  test('changes asset tabs without closing the modal and hides the image footer on Fonts', async () => {
    await page.goto(`${BASE}/page.html`);
    await openModal('/sys/assets/?asset_tab=images');
    await page.waitForSelector('#universalDynamicModalFooter [data-image-submit]');

    await clickIn('[data-dlux-modal-nav] a');
    await page.waitForSelector('#universalDynamicModalBody [data-font-list]', { state: 'attached' });

    assert.equal(await modalVisible(), true);
    assert.equal(await page.locator('#universalDynamicModalFooter').evaluate((el) => el.style.display), 'none');
    assert.ok((await page.evaluate(() => window.__fetched.at(-1))).includes('asset_tab=fonts'));
  });

  test('reloads the currently selected tab after its form succeeds', async () => {
    await page.goto(`${BASE}/page.html`);
    await openModal('/sys/assets/?asset_tab=images');
    await clickIn('[data-dlux-modal-nav] a');
    await page.waitForSelector('#universalDynamicModalBody [data-font-submit]');
    const before = await page.evaluate(() => window.__fetched.filter((url) => url.includes('asset_tab=fonts')).length);

    await clickIn('[data-font-submit]');
    await page.waitForFunction((count) => (
      window.__fetched.filter((url) => url.includes('asset_tab=fonts')).length >= count + 2
    ), before);

    assert.ok((await page.evaluate(() => window.__fetched.at(-1))).includes('asset_tab=fonts'));
  });

  test('submits selected images and renames a grid title inline', async () => {
    await page.goto(`${BASE}/page.html`);
    await openModal('/sys/assets/?asset_tab=images');
    await page.waitForSelector('#universalDynamicModalBody [data-managed-image-input]');
    const before = await page.evaluate(() => window.__fetched.filter((url) => url.includes('asset_tab=images')).length);

    await page.locator('[data-managed-image-input]').setInputFiles({
      name: 'brand.png',
      mimeType: 'image/png',
      buffer: Buffer.from('image'),
    });
    await page.waitForFunction((count) => (
      window.__fetched.filter((url) => url.includes('asset_tab=images')).length >= count + 2
    ), before);

    await page.click('[data-managed-image-title]');
    await page.locator('[data-managed-image-title-input]').fill('Renamed image');
    await page.locator('[data-managed-image-title-input]').press('Enter');
    await page.waitForFunction(() => (
      document.querySelector('[data-managed-image-title]').textContent === 'Renamed image'
    ));
    assert.ok((await page.evaluate(() => window.__fetched.at(-1))).includes('/rename/7/'));
  });
});

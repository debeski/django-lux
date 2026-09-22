// Footer fields must still be submitted after the dynamic modal pins the action bar.
//
// dynamic_modal_form.html renders `dlux_footer_bound_fields` (the `is_active`
// toggle) inside `.dlux-form-actions`, and syncModalFooter() moves that bar into
// the sticky modal footer -- outside the <form>. It re-associated only buttons, so
// the toggle dropped out of FormData and Django read the absent checkbox as False:
// every modal create or edit saved the record inactive, and it vanished from
// active-only lists and pickers while still tripping unique checks.
//
// Driven against the shipped helpers with a stubbed fetch, because the loss
// happens in the browser before any request reaches the server.
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
const PORT = 8733;
const BASE = `http://localhost:${PORT}`;

// The markup dynamic_modal_form.html produces for a form with a footer field.
const FORM = `<form method="post" class="dlux-form" action="/app-modals/storage/Asset/new/" data-dlux-unsaved-guard>
  <input type="hidden" name="csrfmiddlewaretoken" value="token">
  <input type="text" name="name" value="Coffee">
  <div class="dlux-form-actions dlux-form-actions--with-fields">
    <div class="dlux-form-footer-fields">
      <input type="checkbox" name="is_active" id="id_is_active" checked>
    </div>
    <div class="dlux-form-action-buttons">
      <button type="submit" class="dlux-form-action-primary">Add</button>
    </div>
  </div>
</form>`;

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
  window.__posted = [];
  window.fetch = function (url, options) {
    if (options && options.method === 'POST') {
      window.__posted.push(Array.from(options.body.entries()));
      const payload = JSON.stringify({ success: true, reload_current: true });
      return Promise.resolve({ ok: true, text: () => Promise.resolve(payload) });
    }
    const html = ${JSON.stringify(FORM)};
    return Promise.resolve({
      ok: true,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ html }),
      text: () => Promise.resolve(html),
    });
  };
</script>
<script src="/dlux/helpers/dynamic_modal/js/main.js"></script>
<script src="/dlux/system/js/unsaved_guard.js"></script>
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

const openForm = async () => {
  await page.goto(`${BASE}/page.html`);
  await page.evaluate(() => {
    document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
      detail: { data: { url: '/app-modals/storage/Asset/new/', title: 'T' } },
    }));
  });
  await page.waitForSelector('#universalDynamicModalFooter #id_is_active', { state: 'attached' });
};

// Dlux switches hide the real <input>, so set it the way a click would.
const setActive = (checked) => page.evaluate((value) => {
  const box = document.getElementById('id_is_active');
  box.checked = value;
  box.dispatchEvent(new Event('change', { bubbles: true }));
}, checked);

const submit = async () => {
  await page.click('#universalDynamicModalFooter [type="submit"]');
  await page.waitForFunction(() => window.__posted.length === 1);
  return page.evaluate(() => window.__posted[0]);
};

describe('dynamic modal footer fields', () => {
  test('the pinned footer field is associated back to the form', async () => {
    await openForm();
    const associated = await page.evaluate(() => {
      const box = document.getElementById('id_is_active');
      return { outside: !box.closest('form'), owner: box.form && box.form.action };
    });
    assert.equal(associated.outside, true, 'the toggle should sit in the pinned footer');
    assert.ok(associated.owner && associated.owner.endsWith('/app-modals/storage/Asset/new/'));
  });

  test('a checked footer toggle is posted', async () => {
    await openForm();
    const posted = await submit();
    assert.deepEqual(posted.filter(([name]) => name === 'is_active'), [['is_active', 'on']]);
    assert.deepEqual(posted.filter(([name]) => name === 'name'), [['name', 'Coffee']]);
  });

  test('an unchecked footer toggle is still left out', async () => {
    await openForm();
    await setActive(false);
    const posted = await submit();
    assert.equal(posted.some(([name]) => name === 'is_active'), false);
  });

  test('the unsaved guard sees a change to the footer toggle', async () => {
    await openForm();
    const [before, after] = await page.evaluate(() => {
      const form = document.querySelector('#universalDynamicModalBody form');
      const snapshot = window.dluxUnsavedGuard.serialize(form);
      const box = document.getElementById('id_is_active');
      box.checked = false;
      return [snapshot, window.dluxUnsavedGuard.serialize(form)];
    });
    assert.ok(JSON.parse(before).is_active, 'baseline should include the footer toggle');
    assert.notEqual(before, after);
  });
});

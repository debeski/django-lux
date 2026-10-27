// Closing a dirty dynamic modal must save at most once.
//
// A click on the modal's × (data-bs-dismiss) asks Bootstrap to hide the modal
// twice: Bootstrap's own dismiss handler and dynamic_modal's click listener both
// call hide(). The unsaved guard cancelled both and opened its prompt for each,
// binding the prompt's buttons twice, so "Save changes" submitted the form twice
// (two records with the same next number; on a stack that rejects the duplicate,
// the entry looked cancelled).
//
// Driven against the shipped helpers with a stubbed fetch.
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
const TEMPLATES = path.join(HERE, '..', 'dlux', 'templates', 'dlux');
const PORT = 8734;
const BASE = `http://localhost:${PORT}`;

const FORM = `<form method="post" class="dlux-form" action="/records/new/" data-dlux-unsaved-guard>
  <input type="hidden" name="csrfmiddlewaretoken" value="token">
  <input type="text" name="title" id="id_title" value="">
  <div class="dlux-form-actions">
    <div class="dlux-form-action-buttons">
      <button type="submit" class="dlux-form-action-primary">Add</button>
    </div>
  </div>
</form>`;

// The shipped prompt, with its template defaults in place of the strings.
const PROMPT = fs.readFileSync(path.join(TEMPLATES, 'system', 'unsaved_changes_modal.html'), 'utf-8')
  .replace(/\{\{[^}]*default:'([^']*)'[^}]*\}\}/g, '$1')
  .replace(/\{\{[^}]*default:"([^"]*)"[^}]*\}\}/g, '$1');

const PAGE = `<!doctype html><html><head><meta charset="utf-8"></head><body>
<div class="modal fade" id="universalDynamicModal" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content">
    <div class="modal-header">
      <span id="dynamicModalTitleText"></span>
      <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close" id="modalClose"></button>
    </div>
    <div class="modal-body" id="universalDynamicModalBody"></div>
    <div class="modal-footer" id="universalDynamicModalFooter"></div>
  </div></div>
</div>
${PROMPT}
<script src="/bootstrap/bootstrap.bundle.min.js"></script>
<script>
  window.__posted = 0;
  window.fetch = function (url, options) {
    if (options && options.method === 'POST') {
      window.__posted += 1;
      const payload = JSON.stringify({ success: true, close_modal: true });
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

const openDirtyFormAndClose = async () => {
  await page.goto(`${BASE}/page.html`);
  await page.evaluate(() => {
    document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
      detail: { data: { url: '/records/new/', title: 'New record' } },
    }));
  });
  await page.waitForSelector('#universalDynamicModal.show #id_title');
  // Let the guard take its baseline (it waits a task and a paint).
  await page.waitForFunction(() => document.querySelector('#universalDynamicModalBody form')
    .dataset.dluxUnsavedBaseline !== undefined);
  await page.fill('#id_title', 'Changed');
  await page.click('#modalClose');
  await page.waitForSelector('[data-dlux-unsaved-modal].show [data-dlux-unsaved-save]');
  // Count how often Save asks the form to submit. Chromium can drop a second
  // back-to-back requestSubmit() here, but the real document modal does not,
  // so a duplicate POST alone is not a reliable signal.
  await page.evaluate(() => {
    window.__requested = 0;
    const form = document.querySelector('#universalDynamicModalBody form');
    const requestSubmit = form.requestSubmit.bind(form);
    form.requestSubmit = (submitter) => { window.__requested += 1; return requestSubmit(submitter); };
  });
};

describe('closing a dirty dynamic modal', () => {
  test('Save changes submits the form exactly once', async () => {
    await openDirtyFormAndClose();
    await page.click('[data-dlux-unsaved-modal] [data-dlux-unsaved-save]');
    await page.waitForFunction(() => window.__posted > 0);
    await page.waitForTimeout(500);
    assert.equal(await page.evaluate(() => window.__requested), 1, 'Save asked the form to submit more than once');
    assert.equal(await page.evaluate(() => window.__posted), 1);
  });

  test('Discard changes closes the modal without submitting', async () => {
    await openDirtyFormAndClose();
    await page.click('[data-dlux-unsaved-modal] [data-dlux-unsaved-discard]');
    await page.waitForFunction(() => !document.querySelector('#universalDynamicModal.show'));
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => window.__posted), 0);
    assert.equal(await page.evaluate(() => !!document.querySelector('[data-dlux-unsaved-modal].show')), false);
  });

  test('Go back keeps the modal open and can still save once', async () => {
    await openDirtyFormAndClose();
    await page.click('[data-dlux-unsaved-modal] .modal-footer [data-dlux-unsaved-stay]');
    await page.waitForFunction(() => !document.querySelector('[data-dlux-unsaved-modal].show'));
    assert.equal(await page.evaluate(() => !!document.querySelector('#universalDynamicModal.show')), true);
    await page.click('#modalClose');
    await page.waitForSelector('[data-dlux-unsaved-modal].show [data-dlux-unsaved-save]');
    await page.click('[data-dlux-unsaved-modal] [data-dlux-unsaved-save]');
    await page.waitForFunction(() => window.__posted > 0);
    await page.waitForTimeout(500);
    assert.equal(await page.evaluate(() => window.__requested), 1, 'a reopened prompt kept stale Save handlers');
    assert.equal(await page.evaluate(() => window.__posted), 1);
  });
});

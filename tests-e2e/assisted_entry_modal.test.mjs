// Assisted entry must reach forms that a modal injects as its top-level node.
//
// sticky/js/main.js watches for added nodes containing a form, but scanned only
// *inside* the added node (`querySelectorAll('form')`). Dlux's own modal template
// wraps its form in a div, so it worked there; a project template whose root
// element is the <form> itself (Archive's document modal) never got the
// assist bar. The observer also stopped at the first form-bearing node of a
// batch, skipping any later one.
//
// Also covers the dynamic modal's title fallback, which was a hard-coded Arabic
// string shown to English interfaces.
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
const PORT = 8734;
const BASE = `http://localhost:${PORT}`;

const STICKY_FORM = '<form data-app-label="documents" data-model-name="outgoing"><input name="title"></form>';

const PAGE = `<!doctype html><html><head><meta charset="utf-8"></head><body>
<div class="modal fade" id="universalDynamicModal" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content">
    <div class="modal-header"><span id="dynamicModalTitleText"></span></div>
    <div class="modal-body" id="universalDynamicModalBody"></div>
    <div class="modal-footer" id="universalDynamicModalFooter"></div>
  </div></div>
</div>
<div id="host"></div>
<script src="/bootstrap/bootstrap.bundle.min.js"></script>
<script>
  window.DLUX_STRINGS = { modal_default_title: 'Details' };
  window.USER_PREFS = {};
  window.fetch = function () {
    const html = ${JSON.stringify(STICKY_FORM)};
    return Promise.resolve({
      ok: true,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ html }),
      text: () => Promise.resolve(html),
    });
  };
</script>
<script src="/dlux/helpers/sticky/js/main.js"></script>
<script src="/dlux/helpers/dynamic_modal/js/main.js"></script>
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

const barCount = () => page.evaluate(() => document.querySelectorAll('#host [data-dlux-assist-bar]').length);

describe('assisted entry on injected forms', () => {
  test('a form added as the root node gets the assist bar', async () => {
    await page.goto(`${BASE}/page.html`);
    await page.evaluate((html) => {
      const holder = document.createElement('template');
      holder.innerHTML = html;
      document.getElementById('host').appendChild(holder.content.firstElementChild);
    }, STICKY_FORM);
    await page.waitForFunction(() => document.querySelector('#host form [data-dlux-assist-bar]'));
    assert.equal(await barCount(), 1);
  });

  test('every form-bearing node of one batch is scanned', async () => {
    await page.goto(`${BASE}/page.html`);
    await page.evaluate((html) => {
      const host = document.getElementById('host');
      host.innerHTML = `<div><form><input name="search"></form></div>${html}`;
    }, STICKY_FORM);
    await page.waitForFunction(() => document.querySelector('#host form[data-model-name] [data-dlux-assist-bar]'));
    assert.equal(await barCount(), 1, 'only the sticky-capable form gets a bar');
  });

  test('a modal opened without a title uses the translated default', async () => {
    await page.goto(`${BASE}/page.html`);
    await page.evaluate(() => {
      document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
        detail: { data: { url: '/documents/outgoing/manage/?action=add' } },
      }));
    });
    await page.waitForSelector('#universalDynamicModal form', { state: 'attached' });
    assert.equal(await page.textContent('#dynamicModalTitleText'), 'Details');
  });
});

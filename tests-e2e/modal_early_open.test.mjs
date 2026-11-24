// A page script that asks for the dynamic modal while the page loads.
//
// A project opening a modal from a ?modal= deep link dispatched
// dlux:dynamic_modal:open on DOMContentLoaded (Trademarks), or as its own
// non-deferred script ran. The modal's script is deferred and used to start
// listening inside its own DOMContentLoaded handler, so both requests were lost
// and the modal never opened. base_head.js now keeps early requests and
// dynamic_modal/js/main.js starts when the document is parsed, then replays them.
//
// Driven against the shipped scripts with a stubbed fetch.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after } from 'node:test';
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

const PROJECT_SCRIPTS = {
  // A non-deferred script in the scripts block, asking as it runs.
  load: `document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', { detail: { data: { url: '/records/7/?action=view', title: 'Record 7' } } }));`,
  // The Trademarks shape: asks on DOMContentLoaded.
  ready: `document.addEventListener('DOMContentLoaded', function () {
    document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', { detail: { data: { url: '/records/7/?action=view', title: 'Record 7' } } }));
  });`,
};

const page = (mode) => `<!doctype html><html><head><meta charset="utf-8">
<script src="/dlux/base/js/base_head.js"></script>
</head><body>
<div class="modal fade" id="universalDynamicModal" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content">
    <div class="modal-header"><button type="button" id="dynamicModalBack" hidden>back</button><span id="dynamicModalTitleText"></span></div>
    <div class="modal-body" id="universalDynamicModalBody"></div>
    <div class="modal-footer" id="universalDynamicModalFooter"></div>
  </div></div>
</div>
<script>
  window.__fetched = [];
  window.fetch = function (url) {
    window.__fetched.push(String(url));
    const html = '<div data-record="7">record 7</div>';
    return Promise.resolve({ ok: true, json: () => Promise.resolve({ html }) });
  };
</script>
<script src="/bootstrap/bootstrap.bundle.min.js"></script>
<script>${PROJECT_SCRIPTS[mode]}</script>
<script src="/dlux/helpers/dynamic_modal/js/main.js" defer></script>
</body></html>`;

let server;
let browser;

before(async () => {
  server = http.createServer((req, res) => {
    const url = req.url.split('?')[0];
    const mode = url.replace(/^\/page-/, '').replace(/\.html$/, '');
    if (PROJECT_SCRIPTS[mode]) {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      return res.end(page(mode));
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
}, { timeout: 120000 });

after(async () => {
  if (browser) await browser.close();
  if (server) await new Promise((resolve) => server.close(resolve));
});

for (const [mode, label] of [['load', 'as a page script runs'], ['ready', 'on DOMContentLoaded']]) {
  test(`a modal asked for ${label} opens`, async () => {
    const tab = await browser.newPage();
    const errors = [];
    tab.on('pageerror', (error) => errors.push(error.message));
    try {
      await tab.goto(`${BASE}/page-${mode}.html`);
      await tab.waitForFunction(
        () => document.getElementById('universalDynamicModal').classList.contains('show')
          && !!document.querySelector('#universalDynamicModalBody [data-record="7"]'),
        null, { timeout: 4000 });
      const state = await tab.evaluate(() => ({
        fetched: window.__fetched,
        title: document.getElementById('dynamicModalTitleText').textContent,
        queue: window.DluxModalRequests,
      }));
      assert.deepEqual(state.fetched, ['/records/7/?action=view'], 'requested once');
      assert.equal(state.title, 'Record 7');
      assert.equal(state.queue, null, 'the modal took over the queue');
      assert.deepEqual(errors, []);
    } finally {
      await tab.close();
    }
  });
}

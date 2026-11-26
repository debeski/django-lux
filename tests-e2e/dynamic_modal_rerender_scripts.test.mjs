// A modal form refused by validation comes back as fresh markup. Its scripts run
// again under the page nonce, exactly as on first load, and the submit handler is
// bound once per render, not stacked.
//
// The bootstrap mirrors a consumer's form bootstrap: a nonce'd inline script that
// initialises every marker it has not seen yet. Each response carries its own
// nonce, as a Django response does.
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

const PAGE_NONCE = 'page-nonce-123';
const POLICY = (nonce) => `default-src 'self'; script-src 'self' 'nonce-${nonce}'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:`;

const PAGE = `<!doctype html><html><head><meta charset="utf-8">
<script src="/static/dlux/base/js/base_head.js" nonce="${PAGE_NONCE}"></script>
<script type="application/json" id="dlux-asset-bundles">{}</script>
<script src="/static/dlux/base/js/lazy.js" nonce="${PAGE_NONCE}" defer></script>
</head><body>
<div class="modal fade" id="universalDynamicModal" tabindex="-1">
  <div class="modal-dialog"><div class="modal-content">
    <div class="modal-header"><button type="button" id="dynamicModalBack" hidden>back</button><span id="dynamicModalTitleText"></span></div>
    <div class="modal-body" id="universalDynamicModalBody"></div>
    <div class="modal-footer" id="universalDynamicModalFooter"></div>
  </div></div>
</div>
<script src="/static/bootstrap/bootstrap.bundle.min.js" nonce="${PAGE_NONCE}"></script>
<script src="/static/dlux/helpers/dynamic_modal/js/main.js" nonce="${PAGE_NONCE}" defer></script>
</body></html>`;

const FORM = (nonce, render) => `<form method="post" action="/modal-form" data-render="${render}">
  ${render > 1 ? '<div class="invalid-feedback d-block" data-error>This field is required.</div>' : ''}
  <input name="title" value="">
  <div class="js-form-init d-none" data-render="${render}"></div>
  <script nonce="${nonce}">(function(){document.querySelectorAll('.js-form-init:not([data-inited])').forEach(function(m){m.setAttribute('data-inited','1');window.__boots=(window.__boots||[]);window.__boots.push(m.dataset.render);});})();</script>
  <button type="submit" id="save">Save</button>
</form>`;

describe('dynamic modal: re-rendered form markup', { concurrency: 1 }, () => {
  let server;
  let browser;
  let port;
  let posts = 0;
  let served = 0;

  before(async () => {
    server = http.createServer((req, res) => {
      const url = req.url.split('?')[0];
      if (url === '/page') {
        res.writeHead(200, { 'Content-Type': 'text/html', 'Content-Security-Policy': POLICY(PAGE_NONCE) });
        res.end(PAGE);
        return;
      }
      if (url === '/modal-form') {
        if (req.method === 'POST') posts += 1;
        served += 1;
        const nonce = `response-nonce-${served}`;
        req.resume();
        req.on('end', () => {
          res.writeHead(200, { 'Content-Type': 'application/json', 'Content-Security-Policy': POLICY(nonce) });
          const html = FORM(nonce, served);
          res.end(JSON.stringify(req.method === 'POST' ? { success: false, html } : { html }));
        });
        return;
      }
      const file = path.join(STATIC, url.replace(/^\/static\//, '/'));
      if (!file.startsWith(STATIC) || !fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': file.endsWith('.css') ? 'text/css' : 'application/javascript' });
      res.end(fs.readFileSync(file));
    });
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    port = server.address().port;
    browser = await chromium.launch();
  });

  after(async () => {
    await browser?.close();
    await new Promise((resolve) => server.close(resolve));
  });

  test('a refused submit runs the re-rendered bootstrap once, under the page nonce', async () => {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(`THROWN: ${e}`));
    await page.addInitScript(() => {
      window.__cspViolations = [];
      document.addEventListener('securitypolicyviolation', (event) => {
        window.__cspViolations.push(`${event.effectiveDirective} ${event.blockedURI}`);
      });
    });
    try {
      await page.goto(`http://127.0.0.1:${port}/page`, { waitUntil: 'networkidle' });
      await page.evaluate(() => document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
        detail: { data: { url: '/modal-form', title: 'Form' } },
      })));
      await page.waitForSelector('#universalDynamicModalBody .js-form-init[data-inited]', { state: 'attached', timeout: 5000 });
      assert.deepEqual(await page.evaluate(() => window.__boots), ['1'], 'first load ran its bootstrap');

      for (const render of ['2', '3']) {
        const before = posts;
        await page.click('#save');
        await page.waitForSelector(`#universalDynamicModalBody form[data-render="${render}"] [data-error]`, { timeout: 5000 });
        await page.waitForSelector(`#universalDynamicModalBody .js-form-init[data-render="${render}"][data-inited]`,
          { state: 'attached', timeout: 2000 }).catch(() => {});
        assert.equal(posts - before, 1, `render ${render}: one POST per click, so one submit handler`);
        assert.equal(
          await page.evaluate((r) => !!document.querySelector(`.js-form-init[data-render="${r}"][data-inited]`), render),
          true, `render ${render}: the re-rendered bootstrap ran`,
        );
      }

      assert.deepEqual(await page.evaluate(() => window.__boots), ['1', '2', '3'], 'each render booted exactly once');
      assert.deepEqual(await page.evaluate(() => window.__cspViolations), []);
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
});

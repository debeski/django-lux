// DjangoLux under the nonce-only script-src a generated project sends.
//
// settings.py gives the harness the scaffold's policy: `script-src 'self'
// 'nonce-…'`, no 'unsafe-inline', no 'unsafe-eval'. Every page here must load
// without one CSP violation, PDF.js included.
//
// The dynamic modal runs the scripts its fetched markup carries. A script that
// carries the nonce of the response it came in runs under the page's nonce; one
// smuggled into the markup without it does not.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { startServer, loggedInPage, BASE, chromium } from './server.mjs';
import { ROUTES } from './routes.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.join(HERE, '..', 'dlux', 'static');

// Records every CSP violation the page reports, from the first script on.
const WATCH = () => {
  window.__cspViolations = [];
  document.addEventListener('securitypolicyviolation', (event) => {
    window.__cspViolations.push(`${event.effectiveDirective} ${event.blockedURI} ${event.sample || ''}`.trim());
  });
};
const violations = (page) => page.evaluate(() => window.__cspViolations || []);

describe('DjangoLux pages', { concurrency: 1 }, () => {
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

  test('the policy is nonce-only', async () => {
    const response = await fetch(`${BASE}/accounts/login/`);
    const policy = response.headers.get('content-security-policy') || '';
    const scriptSrc = policy.split(';').map((part) => part.trim()).find((part) => part.startsWith('script-src')) || '';
    assert.match(scriptSrc, /^script-src 'self' 'nonce-[A-Za-z0-9+/=]+'$/);
  });

  test('every page loads without a CSP violation', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    await ctx.addInitScript(WATCH);
    try {
      const routes = ROUTES.filter((route) => route.phase === 'main').map((route) => route.path);
      for (const route of [...routes, '/sys/options/?tab=appearance']) {
        await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle' });
        assert.deepEqual(await violations(page), [], route);
      }
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a modal loaded into a page runs its scripts', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    await ctx.addInitScript(WATCH);
    try {
      await page.goto(`${BASE}/sys/users/`, { waitUntil: 'networkidle' });
      await page.evaluate(() => document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
        detail: { data: { url: '/sys/modals/users/', title: 'User' } },
      })));
      await page.waitForSelector('#universalDynamicModalBody form', { timeout: 10000 });
      await page.waitForLoadState('networkidle');
      assert.deepEqual(await violations(page), []);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

// A static server that sends the policy itself, so the test controls each nonce.
const PAGE_NONCE = 'page-nonce-123';
const RESPONSE_NONCE = 'response-nonce-456';
const POLICY = (nonce) => `default-src 'self'; script-src 'self' 'nonce-${nonce}'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:`;

const MODAL_PAGE = `<!doctype html><html><head><meta charset="utf-8">
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

const MODAL_BODY = JSON.stringify({
  html: `<div data-modal-ready>ready</div>
<script nonce="${RESPONSE_NONCE}">window.__trusted = (window.__trusted || 0) + 1;</script>
<script src="/e2e/modal_src.js" nonce="${RESPONSE_NONCE}"></script>
<script>window.__smuggled = 1;</script>
<script nonce="guessed">window.__guessed = 1;</script>
<script type="application/json" id="modal-data">{"kept": true}</script>`,
});

const VIEWER_PAGE = (viewer) => `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/bootstrap/bootstrap.min.css">
<link rel="stylesheet" href="/static/dlux/pdf/css/main.css">
</head><body><div style="width:520px">${viewer}</div>
<script type="application/json" id="dlux-asset-bundles">${JSON.stringify({ pdf: { css: [], js: ['/static/dlux/pdf/vendor/pdf.min.js'] } })}</script>
<script src="/static/dlux/base/js/lazy.js" nonce="${PAGE_NONCE}"></script>
<script src="/static/dlux/pdf/js/pdfjs.js" nonce="${PAGE_NONCE}"></script>
<script src="/static/dlux/pdf/js/viewer.js" nonce="${PAGE_NONCE}"></script>
</body></html>`;

describe('under a policy the test controls', { concurrency: 1 }, () => {
  let server;
  let browser;
  let port;
  let viewer;

  before(async () => {
    const { execFileSync } = await import('node:child_process');
    const root = path.join(HERE, '..');
    viewer = execFileSync(path.join(root, '.venv', 'bin', 'python'), ['-c', `
import django; django.setup()
from types import SimpleNamespace
from django.template.loader import render_to_string
print(render_to_string('dlux/pdf/viewer.html', {
    'source_url': '/fixtures/two-pages.pdf', 'download_url': '/fixtures/two-pages.pdf', 'file_name': 'two-pages.pdf',
    'pdf_features': {'editing_enabled': False, 'history_enabled': False},
    'request': SimpleNamespace(csp_nonce='${PAGE_NONCE}'),
}))
`], { cwd: root, env: { ...process.env, DJANGO_SETTINGS_MODULE: 'dlux.tests.settings', PYTHONPATH: root } }).toString();

    server = http.createServer((req, res) => {
      const url = req.url.split('?')[0];
      if (url === '/modal' || url === '/viewer') {
        res.writeHead(200, { 'Content-Type': 'text/html', 'Content-Security-Policy': POLICY(PAGE_NONCE) });
        res.end(url === '/modal' ? MODAL_PAGE : VIEWER_PAGE(viewer));
        return;
      }
      if (url === '/modal-body') {
        res.writeHead(200, { 'Content-Type': 'application/json', 'Content-Security-Policy': POLICY(RESPONSE_NONCE) });
        res.end(MODAL_BODY);
        return;
      }
      if (url === '/e2e/modal_src.js') {
        res.writeHead(200, { 'Content-Type': 'application/javascript' });
        res.end('window.__fromSrc = 1;');
        return;
      }
      const root = url.startsWith('/fixtures/') ? path.join(HERE, 'fixtures') : STATIC;
      const file = path.join(root, url.replace(/^\/(static|fixtures)\//, '/'));
      if (!file.startsWith(root) || !fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
      const type = file.endsWith('.css') ? 'text/css' : file.endsWith('.pdf') ? 'application/pdf'
        : file.endsWith('.woff2') ? 'font/woff2' : 'application/javascript';
      res.writeHead(200, { 'Content-Type': type });
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

  test('the modal runs the scripts its response vouches for, and only those', async () => {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(`THROWN: ${e}`));
    await page.addInitScript(WATCH);
    try {
      await page.goto(`http://127.0.0.1:${port}/modal`, { waitUntil: 'networkidle' });
      await page.evaluate(() => document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
        detail: { data: { url: '/modal-body', title: 'Modal' } },
      })));
      await page.waitForSelector('#universalDynamicModalBody [data-modal-ready]');
      await page.waitForFunction(() => window.__fromSrc === 1, null, { timeout: 5000 });
      const state = await page.evaluate(() => ({
        trusted: window.__trusted,
        fromSrc: window.__fromSrc,
        smuggled: window.__smuggled,
        guessed: window.__guessed,
        json: document.getElementById('modal-data')?.textContent,
      }));
      assert.equal(state.trusted, 1, 'the vouched-for inline script ran once');
      assert.equal(state.fromSrc, 1);
      assert.equal(state.smuggled, undefined, 'a script without the response nonce must not run');
      assert.equal(state.guessed, undefined, 'a script with a guessed nonce must not run');
      assert.equal(state.json, '{"kept": true}');
      const blocked = await violations(page);
      assert.equal(blocked.length, 2, blocked.join('\n'));
      assert.ok(blocked.every((entry) => entry.startsWith('script-src-elem inline')), blocked.join('\n'));
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });

  test('PDF.js renders without eval', async () => {
    const page = await browser.newPage({ viewport: { width: 1000, height: 800 } });
    const errors = [];
    page.on('pageerror', (e) => errors.push(`THROWN: ${e}`));
    await page.addInitScript(WATCH);
    try {
      await page.goto(`http://127.0.0.1:${port}/viewer`, { waitUntil: 'networkidle' });
      await page.waitForFunction(() => Number(document.querySelector('.dlux-pdf-viewer')?.dataset.pdfZoom) === 1,
        null, { timeout: 10000 });
      const drawn = await page.evaluate(() => {
        const canvas = document.querySelector('[data-pdf-canvas], .dlux-pdf-stage canvas');
        return canvas ? canvas.width : 0;
      });
      assert.ok(drawn > 0, 'the page was drawn');
      assert.deepEqual(await violations(page), []);
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
});

// The resident Composer's row in the Updates card.
//
// An icon that checks, a second that appears only when the channel publishes a
// newer Composer, and a tick when it does not. Checking and repairing the
// deployment itself moved to the Operations panel (operations_panel.test.mjs).
// DOM state driven by a JSON payload, so it is driven here in a real browser
// against the shipped file, with the state endpoint stubbed.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.join(HERE, '..', 'dlux', 'static');
const PORT = 8742;
const BASE = `http://localhost:${PORT}`;

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><meta name="csrf-token" content="tok"></head>
<body>
<div class="dlux-ops" data-dlux-ops data-state-url="/state.json" data-run-url="/run" data-can-manage="true"
     data-label-agent-update="Update the Composer agent" data-label-agent-update-note="Recreates the pair."
     data-label-last-check="Last check">
  <div class="dlux-upd-row">
    <span class="dlux-upd-lead">
      <button type="button" class="dlux-upd-ic" data-dlux-ops-check="agent-check" title="check Composer"><i class="bi bi-arrow-clockwise" data-dlux-ops-glyph="agent-check"></i></button>
      <button type="button" class="dlux-upd-ic dlux-upd-ic--avail" data-dlux-ops-open="agent-update" hidden><i class="bi bi-arrow-down-circle-fill"></i></button>
      <span class="dlux-upd-name">Resident Composer</span>
      <span class="dlux-upd-ver" data-dlux-ops-composer-version></span><span class="dlux-upd-target" data-dlux-ops-composer-target hidden></span>
    </span>
  </div>
  <div data-dlux-ops-status hidden></div>
</div>
<script src="/dlux/system/js/ops.js"></script>
</body></html>`;

const OPERATIONS = [
  { name: 'agent-check', label: 'Check the resident Composer', changes_deployment: false, needs_preview: false, available: true, unavailable_reason: '' },
  { name: 'agent-update', label: 'Update resident Composer', changes_deployment: true, needs_preview: false, available: true, unavailable_reason: '' },
];

let server;
let browser;
let page;

/** Load the page with `state` served by the stubbed endpoint. */
async function load(state) {
  await page.addInitScript((payload) => {
    window.__posted = [];
    window.__confirms = [];
    window.dluxConfirmPassword = (config) => {
      window.__confirms.push(config.title);
      return config.onConfirm('pw-root-1234', { showError: () => {} });
    };
    const respond = (body) => Promise.resolve({
      ok: true, status: 200, json: () => Promise.resolve(body),
    });
    window.__state = payload;
    window.fetch = (url, options) => {
      if (String(url).includes('/run')) {
        const body = {};
        (options.body || new FormData()).forEach((value, key) => { body[key] = value; });
        window.__posted.push(body);
        return respond({ ok: true, run: { operation: body.operation, status: 'running', active: true } });
      }
      return respond(window.__state);
    };
  }, state);
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.querySelector('[data-dlux-ops-glyph="agent-check"]'));
}

const glyph = (which) => page.locator(`[data-dlux-ops-glyph="${which}"]`).getAttribute('class');
const amber = (action) => page.locator(`[data-dlux-ops-open="${action}"]`);

before(async () => {
  server = http.createServer((req, res) => {
    if (req.url === '/') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(PAGE);
      return;
    }
    const file = path.join(STATIC, req.url.split('?')[0]);
    if (!file.startsWith(STATIC) || !fs.existsSync(file)) {
      res.writeHead(404);
      res.end('not found');
      return;
    }
    res.writeHead(200, { 'Content-Type': 'application/javascript' });
    res.end(fs.readFileSync(file));
  });
  await new Promise((resolve) => server.listen(PORT, resolve));
  browser = await chromium.launch();
  page = await browser.newPage();
});

after(async () => {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
});

describe('the resident Composer row', () => {
  test('a published newer version is offered with its number', async () => {
    await load({ operations: OPERATIONS, run: null, composer_version: '1.5.2',
      resident: { version: '1.5.2', published_version: '1.6.0', channel: 'stable', checked: true, update_available: true } });
    assert.equal(await page.locator('[data-dlux-ops-composer-version]').textContent(), 'v1.5.2');
    assert.equal(await page.locator('[data-dlux-ops-composer-target]').textContent(), 'v1.6.0');
    assert.equal(await amber('agent-update').isVisible(), true);
    assert.match(await glyph('agent-check'), /bi-arrow-clockwise/, 'a pending update is not a tick');
  });

  test('a current Composer is a tick and offers nothing to install', async () => {
    await load({ operations: OPERATIONS, run: null, composer_version: '1.6.0',
      resident: { version: '1.6.0', published_version: '1.6.0', checked: true, update_available: false } });
    assert.match(await glyph('agent-check'), /bi-check-circle-fill/);
    assert.equal(await amber('agent-update').isVisible(), false);
  });

  test('updating confirms with the password through the shared prompt', async () => {
    await load({ operations: OPERATIONS, run: null, composer_version: '1.5.2',
      resident: { version: '1.5.2', published_version: '1.6.0', channel: 'stable', checked: true, update_available: true } });
    await amber('agent-update').click();
    await page.waitForFunction(() => window.__posted.length > 0);
    assert.deepEqual(await page.evaluate(() => window.__posted[0]),
      { operation: 'agent-update', current_password: 'pw-root-1234' });
    assert.deepEqual(await page.evaluate(() => window.__confirms), ['Update resident Composer']);
  });

  test('checking needs no password', async () => {
    await load({ operations: OPERATIONS, run: null, composer_version: '1.5.2',
      resident: { version: '1.5.2', checked: false, update_available: false } });
    await page.locator('[data-dlux-ops-check="agent-check"]').click();
    await page.waitForFunction(() => window.__posted.length > 0);
    assert.deepEqual(await page.evaluate(() => window.__posted[0]), { operation: 'agent-check' });
    assert.equal(await page.evaluate(() => window.__confirms.length), 0);
  });

  test('the row carries its last-check time in its tooltip', async () => {
    await load({ operations: OPERATIONS, run: null, composer_version: '1.5.2',
      resident: { version: '1.5.2', checked: true, update_available: false, checked_at: '2026-09-24T06:26:34Z' } });
    const title = await page.locator('[data-dlux-ops-check="agent-check"]').getAttribute('title');
    assert.match(title, /^check Composer — Last check: /);
  });
});

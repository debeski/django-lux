// The deployment rows in the Updates card.
//
// The rows are the whole feature: an icon that checks, a second that appears
// only when there is something to install, a tick when there is not, and every
// finding in a modal rather than in the card. That is DOM state driven by a
// JSON payload, so it is driven here in a real browser against the shipped
// file, with the state endpoint stubbed.
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

const ROW = (name, check, action, extra = '') => `
<div class="dlux-upd-row">
  <span class="dlux-upd-lead">
    <button type="button" class="dlux-upd-ic" data-dlux-ops-check="${check}" title="check ${name}"><i class="bi bi-arrow-clockwise" data-dlux-ops-glyph="${check}"></i></button>
    <button type="button" class="dlux-upd-ic dlux-upd-ic--avail" data-dlux-ops-open="${action}" hidden><i class="bi bi-arrow-down-circle-fill"></i></button>
    <span class="dlux-upd-name">${name}</span>
    ${extra}
  </span>
</div>`;

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><meta name="csrf-token" content="tok"></head>
<body>
<div class="dlux-ops" data-dlux-ops data-state-url="/state.json" data-run-url="/run" data-can-manage="true"
     data-label-never="Not checked yet" data-label-clean="No problems found"
     data-label-summary="{fail} problem(s), {warn} warning(s)" data-label-apply="Apply">
  ${ROW('Deployment', 'check', 'check-fix-apply', '<span class="dlux-upd-ver" data-dlux-ops-summary></span>')}
  <button type="button" class="dlux-upd-ic" data-dlux-ops-results hidden><i class="bi bi-list-check"></i></button>
  ${ROW('Resident Composer', 'agent-check', 'agent-update',
    '<span class="dlux-upd-ver" data-dlux-ops-composer-version></span><span class="dlux-upd-target" data-dlux-ops-composer-target hidden></span>')}
  <div data-dlux-ops-status hidden></div>
</div>
<div id="dluxOpsResultModal">
  <h5 data-dlux-ops-modal-title>Deployment check</h5>
  <p data-dlux-ops-modal-intro>intro</p>
  <ul data-dlux-ops-findings></ul>
  <div data-dlux-ops-repairs hidden><div data-dlux-ops-diffs></div></div>
  <div data-dlux-ops-confirm hidden><input type="password" data-dlux-ops-password></div>
  <div data-dlux-ops-confirm-note></div>
  <div data-dlux-ops-error hidden></div>
  <button type="button" data-dlux-ops-submit hidden></button>
</div>
<script src="/dlux/system/js/ops.js"></script>
</body></html>`;

const OPERATIONS = [
  { name: 'check', label: 'Run deployment check', changes_deployment: false, needs_preview: false, available: true, unavailable_reason: '' },
  { name: 'agent-check', label: 'Check the resident Composer', changes_deployment: false, needs_preview: false, available: true, unavailable_reason: '' },
  { name: 'agent-update', label: 'Update resident Composer', changes_deployment: true, needs_preview: false, available: true, unavailable_reason: '' },
  { name: 'check-fix-apply', label: 'Apply repairs', changes_deployment: true, needs_preview: true, available: true, unavailable_reason: '' },
];

const CLEAN_CHECK = {
  operation: 'check', status: 'completed', active: false, error: '',
  findings: [{ level: 'ok', name: 'docker', message: 'Docker daemon reachable.' }],
  repairs: [], summary: { total: 1, ok: 1, warn: 0, fail: 0 },
};

const REPAIR_CHECK = {
  operation: 'check', status: 'completed', active: false, error: '',
  findings: [{ level: 'fail', name: 'resident-block', message: 'composer-executor is not defined.' }],
  repairs: [{ name: 'resident-block', files: ['docker-compose.yml'], diff: '+  composer-executor:', note: '' }],
  summary: { total: 1, ok: 0, warn: 0, fail: 1 },
};

let server;
let browser;
let page;

/** Load the page with `state` served by the stubbed endpoint. */
async function load(state) {
  await page.addInitScript((payload) => {
    window.__posted = [];
    window.bootstrap = {
      Modal: class {
        constructor(element) { this.element = element; }
        show() { this.element.dataset.open = 'true'; }
        hide() { this.element.dataset.open = 'false'; }
      },
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
  await page.waitForFunction(() => document.querySelector('[data-dlux-ops-glyph="check"]'));
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

describe('deployment rows', () => {
  test('a deployment nobody has checked offers a check and claims nothing', async () => {
    await load({ operations: OPERATIONS, run: null, check: null, has_preview: false, composer_version: '1.5.2', resident: { version: '1.5.2', checked: false, update_available: false } });
    assert.equal(await page.locator('[data-dlux-ops-summary]').textContent(), 'Not checked yet');
    assert.match(await glyph('check'), /bi-arrow-clockwise/);
    assert.match(await glyph('agent-check'), /bi-arrow-clockwise/, 'unchecked is not "up to date"');
    assert.equal(await amber('check-fix-apply').isVisible(), false);
    assert.equal(await amber('agent-update').isVisible(), false);
    assert.equal(await page.locator('[data-dlux-ops-results]').isVisible(), false);
  });

  test('a clean check becomes a tick and offers no repair', async () => {
    await load({ operations: OPERATIONS, run: CLEAN_CHECK, check: CLEAN_CHECK, has_preview: true, composer_version: '1.5.2', resident: { version: '1.5.2', checked: true, update_available: false } });
    assert.equal(await page.locator('[data-dlux-ops-summary]').textContent(), 'No problems found');
    assert.match(await glyph('check'), /bi-check-circle-fill/);
    assert.match(await glyph('agent-check'), /bi-check-circle-fill/);
    assert.equal(await amber('check-fix-apply').isVisible(), false);
    assert.equal(await page.locator('[data-dlux-ops-results]').isVisible(), true, 'the last check stays readable');
  });

  test('a check with repairs offers them, and the modal carries the diff and the password', async () => {
    await load({ operations: OPERATIONS, run: REPAIR_CHECK, check: REPAIR_CHECK, has_preview: true, composer_version: '1.5.2', resident: { version: '1.5.2', checked: true, update_available: false } });
    assert.equal(await page.locator('[data-dlux-ops-summary]').textContent(), '1 problem(s), 0 warning(s)');
    assert.equal(await amber('check-fix-apply').isVisible(), true);

    await amber('check-fix-apply').click();
    assert.equal(await page.locator('#dluxOpsResultModal').getAttribute('data-open'), 'true');
    assert.equal(await page.locator('[data-dlux-ops-findings] .dlux-ops-finding-message').textContent(),
      'composer-executor is not defined.');
    assert.equal(await page.locator('[data-dlux-ops-diffs] .dlux-ops-diff').textContent(), '+  composer-executor:');
    assert.equal(await page.locator('[data-dlux-ops-confirm]').isVisible(), true);
    assert.equal(await page.locator('[data-dlux-ops-submit]').textContent(), 'Apply repairs');
  });

  test('applying sends the password with the operation, and nothing else does', async () => {
    await load({ operations: OPERATIONS, run: REPAIR_CHECK, check: REPAIR_CHECK, has_preview: true, composer_version: '1.5.2', resident: { version: '1.5.2', checked: true, update_available: false } });
    await amber('check-fix-apply').click();
    await page.locator('[data-dlux-ops-password]').fill('pw-root-1234');
    await page.locator('[data-dlux-ops-submit]').click();
    await page.waitForFunction(() => window.__posted.length > 0);
    assert.deepEqual(await page.evaluate(() => window.__posted[0]),
      { operation: 'check-fix-apply', current_password: 'pw-root-1234' });

    await page.locator('[data-dlux-ops-check="check"]').click();
    await page.waitForFunction(() => window.__posted.length > 1);
    assert.deepEqual(await page.evaluate(() => window.__posted[1]), { operation: 'check' },
      'a read-only check must never ask for a password');
  });

  test('reading the last check offers no action at all', async () => {
    await load({ operations: OPERATIONS, run: CLEAN_CHECK, check: CLEAN_CHECK, has_preview: true, composer_version: '1.5.2', resident: { version: '1.5.2', checked: true, update_available: false } });
    await page.locator('[data-dlux-ops-results]').click();
    assert.equal(await page.locator('[data-dlux-ops-confirm]').isVisible(), false);
    assert.equal(await page.locator('[data-dlux-ops-submit]').isVisible(), false);
  });
});

describe('the resident Composer row', () => {
  test('a published newer version is offered with its number', async () => {
    await load({ operations: OPERATIONS, run: null, check: null, has_preview: false, composer_version: '1.5.2',
      resident: { version: '1.5.2', published_version: '1.6.0', channel: 'stable', checked: true, update_available: true } });
    assert.equal(await page.locator('[data-dlux-ops-composer-version]').textContent(), 'v1.5.2');
    assert.equal(await page.locator('[data-dlux-ops-composer-target]').textContent(), 'v1.6.0');
    assert.equal(await amber('agent-update').isVisible(), true);
    assert.match(await glyph('agent-check'), /bi-arrow-clockwise/, 'a pending update is not a tick');
  });

  test('updating asks for the password only after a check found one', async () => {
    await load({ operations: OPERATIONS, run: null, check: null, has_preview: false, composer_version: '1.5.2',
      resident: { version: '1.5.2', published_version: '1.6.0', channel: 'stable', checked: true, update_available: true } });
    await amber('agent-update').click();
    assert.equal(await page.locator('[data-dlux-ops-confirm]').isVisible(), true);
    assert.equal(await page.locator('[data-dlux-ops-submit]').textContent(), 'Update resident Composer');

    await page.locator('[data-dlux-ops-password]').fill('pw-root-1234');
    await page.locator('[data-dlux-ops-submit]').click();
    await page.waitForFunction(() => window.__posted.length > 0);
    assert.deepEqual(await page.evaluate(() => window.__posted[0]),
      { operation: 'agent-update', current_password: 'pw-root-1234' });
  });

  test('a running operation spins its own row and leaves the other alone', async () => {
    await load({ operations: OPERATIONS, run: null, check: null, has_preview: false, composer_version: '1.5.2',
      resident: { version: '1.5.2', checked: false, update_available: false } });
    await page.locator('[data-dlux-ops-check="agent-check"]').click();
    await page.waitForFunction(() => window.__posted.length > 0);
    assert.equal(await page.locator('[data-dlux-ops-check="check"]').isDisabled(), true,
      'one operation at a time: the other row cannot start a second');
  });
});

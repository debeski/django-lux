// The Updates card through its whole click -> spinner -> poll -> re-render cycle.
//
// ops_rows.test.mjs renders fixed states, so it never meets the shared loading
// button, which REPLACES a button's icon with a spinner while it works and rebuilds
// the button from an HTML snapshot when it stops. A script that kept hold of the
// icon element it found at page load then updates a detached node: the row never
// turns green after a check until the page is reloaded. Here the real scripts run
// with the real helper against a stateful stub of the server.
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
const PORT = 8743;
const BASE = `http://localhost:${PORT}`;

const UPDATER = `
<div class="dlux-updater" data-dlux-updater data-can-manage="true" data-state-url="/u/state" data-check-url="/u/check"
     data-label-last-check="Last check" data-label-image-local="Local build: not compared with the registry"
     data-label-baked-dlux="baked dlux" data-note-baked-dlux="DjangoLux version baked into this image">
  <div class="dlux-upd-row">
    <button type="button" class="dlux-upd-ic" title="Check for updates" aria-label="Check for updates" data-dlux-update-check><i class="bi bi-arrow-clockwise" data-dlux-check-glyph></i></button>
    <button type="button" class="dlux-upd-ic dlux-upd-ic--avail" data-dlux-update-review hidden><i class="bi bi-arrow-down-circle-fill"></i></button>
    <span data-dlux-update-active></span><span data-dlux-update-latest></span>
    <button type="button" data-dlux-update-rollback hidden></button><button type="button" data-dlux-release-notes hidden></button>
  </div>
  <div class="dlux-upd-row">
    <i class="bi bi-check-circle-fill dlux-upd-ic dlux-upd-ic--static dlux-upd-ic--ok" data-dlux-image-ok title="The application image is up to date"></i>
    <button type="button" class="dlux-upd-ic dlux-upd-ic--avail" data-dlux-update-image title="Application update available" hidden><i class="bi bi-arrow-down-circle-fill"></i></button>
    <span data-dlux-image-name>Application</span><span data-dlux-app-version></span>
    <span data-dlux-image-target hidden></span><span data-dlux-image-digest></span>
  </div>
  <div data-dlux-update-run-status></div>
</div>
<div id="dluxUpdateReviewModal">
  <h5 data-dlux-update-modal-title></h5>
  <div data-dlux-update-review-panel>
    <span data-dlux-update-target></span><span data-dlux-update-baked hidden></span>
    <div data-dlux-update-summary></div><div data-dlux-update-compatibility></div><div data-dlux-update-maintenance></div>
    <input type="password" name="current_password">
  </div>
  <div data-dlux-update-progress-panel hidden></div>
  <div data-dlux-update-error hidden></div>
  <button type="button" data-dlux-update-submit></button>
</div>`;

const OPS_ROW = (name, check, action, extra = '') => `
<div class="dlux-upd-row">
  <button type="button" class="dlux-upd-ic" data-dlux-ops-check="${check}" title="check ${name}"><i class="bi bi-arrow-clockwise" data-dlux-ops-glyph="${check}"></i></button>
  <button type="button" class="dlux-upd-ic dlux-upd-ic--avail" data-dlux-ops-open="${action}" hidden><i class="bi bi-arrow-down-circle-fill"></i></button>
  <span class="dlux-upd-name">${name}</span>${extra}
</div>`;

const OPS = `
<div class="dlux-ops" data-dlux-ops data-state-url="/o/state" data-run-url="/o/run" data-can-manage="true"
     data-label-never="Not checked yet" data-label-clean="No problems found"
     data-label-summary="{fail} problem(s), {warn} warning(s)" data-label-apply="Apply" data-label-last-check="Last check"
     data-label-composer-unknown="Could not check for a Composer update: {reason}"
     data-label-no-repair="No automatic repair is available for these findings.">
  ${OPS_ROW('Deployment', 'check', 'check-fix-apply', '<span data-dlux-ops-summary></span>')}
  <button type="button" data-dlux-ops-results hidden><i class="bi bi-list-check"></i></button>
  ${OPS_ROW('Resident Composer', 'agent-check', 'agent-update', '<span data-dlux-ops-composer-version></span><span data-dlux-ops-composer-target hidden></span>')}
  <div data-dlux-ops-composer-notice hidden></div>
  <div data-dlux-ops-status hidden></div>
</div>
<div id="dluxOpsResultModal">
  <h5 data-dlux-ops-modal-title>Deployment check</h5><p data-dlux-ops-modal-intro>intro</p>
  <ul data-dlux-ops-findings></ul>
  <div data-dlux-ops-norepair hidden></div>
  <div data-dlux-ops-repairs hidden><div data-dlux-ops-diffs></div></div>
  <div data-dlux-ops-confirm hidden><input type="password" data-dlux-ops-password></div>
  <div data-dlux-ops-confirm-note></div><div data-dlux-ops-error hidden></div>
  <button type="button" data-dlux-ops-offer hidden>Apply repairs</button>
  <button type="button" data-dlux-ops-submit hidden></button>
</div>`;

const page_html = (body, scripts) => `<!doctype html><html><head><meta charset="utf-8"><meta name="csrf-token" content="tok"></head>
<body>${body}${scripts.map((s) => `<script src="${s}"></script>`).join('')}</body></html>`;

const PAGES = {
  '/updater': page_html(UPDATER, ['/dlux/helpers/loading_button/js/main.js', '/dlux/system/js/updater.js']),
  '/ops': page_html(OPS, ['/dlux/helpers/loading_button/js/main.js', '/dlux/system/js/ops.js']),
};

const OPERATIONS = [
  { name: 'check', label: 'Run deployment check', changes_deployment: false, needs_preview: false, available: true, unavailable_reason: '' },
  { name: 'agent-check', label: 'Check the resident Composer', changes_deployment: false, needs_preview: false, available: true, unavailable_reason: '' },
  { name: 'agent-update', label: 'Update resident Composer', changes_deployment: true, needs_preview: false, available: true, unavailable_reason: '' },
  { name: 'check-fix-apply', label: 'Apply repairs', changes_deployment: true, needs_preview: true, available: true, unavailable_reason: '' },
];

let server;
let browser;
let page;

before(async () => {
  server = http.createServer((req, res) => {
    const url = req.url.split('?')[0];
    if (PAGES[url]) {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(PAGES[url]);
      return;
    }
    const file = path.join(STATIC, url);
    if (!file.startsWith(STATIC) || !fs.existsSync(file)) { res.writeHead(404); res.end('not found'); return; }
    res.writeHead(200, { 'Content-Type': 'application/javascript' });
    res.end(fs.readFileSync(file));
  });
  await new Promise((resolve) => server.listen(PORT, resolve));
  browser = await chromium.launch();
});

after(async () => {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
});

/** A stateful stand-in for the server: `script` decides how each request is answered. */
async function open(route, script, initial) {
  page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(({ body, init }) => {
    window.bootstrap = { Modal: class { constructor(e) { this.e = e; } show() { this.e.dataset.open = 'true'; } hide() { this.e.dataset.open = 'false'; } } };
    window.__server = init;
    window.__posted = [];
    window.__calls = {};
    const reply = (payload) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(payload) });
    window.fetch = (url, options = {}) => {
      const key = String(url);
      window.__calls[key] = (window.__calls[key] || 0) + 1;
      if (options.method === 'POST') {
        const body = {};
        (options.body || new FormData()).forEach((v, k) => { body[k] = v; });
        window.__posted.push({ url: key, body });
      }
      return reply(window.__respond(key, options, window.__calls[key]));
    };
    window.__respond = new Function('url', 'options', 'n', body);
  }, { body: script, init: initial });
  await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle' });
  return errors;
}

const closePage = async () => { await page?.close(); };

const UPDATER_STATE = (over = {}) => ({
  active_version: '1.10.0', latest_version: '1.10.0', latest_compatible: false, last_checked_at: null,
  last_check_error: '', previous_version: '', skipped_versions: [], update_channel: 'stable', can_manage: true,
  image: { image: 'debeski/dlux-crm:sales', app_version: '0.9.0', running_digest: 'sha256:aaaaaaaaaaaaaaaa', checked_at: '' },
  image_update_available: false, image_update_target: '', ...over,
});

const UPDATER_SCRIPT = `
  const s = window.__server;
  if (url === '/u/state') return { ok: true, state: s.state, run: null, image_update: null };
  if (url === '/u/check') return { ok: true, run: { token: 't1', action: 'check', status: 'checking', active: true }, run_url: '/u/runs/t1/', state: s.state };
  if (url === '/u/runs/t1/') {
    if (n < 2) return { ok: true, run: { token: 't1', action: 'check', status: 'checking', active: true } };
    s.state = { ...s.state, last_checked_at: new Date().toISOString() };
    return { ok: true, run: { token: 't1', action: 'check', status: 'completed', active: false } };
  }
  return { ok: true };`;

describe('the DjangoLux row', () => {
  test('a check that finds nothing newer turns the row green without a reload', async () => {
    const errors = await open('/updater', UPDATER_SCRIPT, { state: UPDATER_STATE() });
    const icon = () => page.locator('[data-dlux-update-check] i').getAttribute('class');
    assert.match(await icon(), /bi-arrow-clockwise/, 'never checked yet: the arrow');

    await page.locator('[data-dlux-update-check]').click();
    await page.waitForFunction(() => window.__calls['/u/runs/t1/'] >= 2
      && !document.querySelector('[data-dlux-update-check]').classList.contains('dlux-btn--loading'), null, { timeout: 12000 });

    assert.match(await icon(), /bi-check-circle-fill/, 'the tick replaces the arrow once the check is done');
    assert.equal(await page.locator('[data-dlux-update-check]').evaluate((el) => el.classList.contains('is-ok')), true);
    assert.deepEqual(errors, []);
    await closePage();
  });

  test('a row that was already checked is green from the start, and stays green after a re-check', async () => {
    await open('/updater', UPDATER_SCRIPT, { state: UPDATER_STATE({ last_checked_at: '2026-09-30T10:00:00Z' }) });
    const icon = () => page.locator('[data-dlux-update-check] i').getAttribute('class');
    assert.match(await icon(), /bi-check-circle-fill/);
    await page.locator('[data-dlux-update-check]').click();
    await page.waitForFunction(() => window.__calls['/u/runs/t1/'] >= 2
      && !document.querySelector('[data-dlux-update-check]').classList.contains('dlux-btn--loading'), null, { timeout: 12000 });
    assert.match(await icon(), /bi-check-circle-fill/);
    await closePage();
  });
});

describe('the application image row', () => {
  test('a locally built image is not offered the registry image as an update', async () => {
    await open('/updater', UPDATER_SCRIPT, { state: UPDATER_STATE({
      last_checked_at: '2026-09-30T10:00:00Z',
      image: { image: 'debeski/dlux-crm:sales', app_version: '0.9.0', running_digest: '', local_build: true, checked_at: '' },
    }) });
    assert.equal(await page.locator('[data-dlux-update-image]').isVisible(), false);
    const ok = page.locator('[data-dlux-image-ok]');
    assert.equal(await ok.evaluate((el) => el.hidden), false, 'the row still says something');
    assert.match(await ok.getAttribute('title'), /Local build/);
    assert.doesNotMatch(await ok.getAttribute('class'), /dlux-upd-ic--ok\b/, 'a local build is not "up to date" either');
    await closePage();
  });

  test('an available update names its own build, and DjangoLux is labelled as DjangoLux', async () => {
    await open('/updater', UPDATER_SCRIPT, { state: UPDATER_STATE({
      last_checked_at: '2026-09-30T10:00:00Z',
      image_update_available: true, image_update_target: 'sha256:9c4b81108b54', image_update_baked_dlux: '1.10.0',
    }) });
    assert.equal(await page.locator('[data-dlux-image-target]').textContent(), '→ sha256:9c4b81108b54');
    await page.locator('[data-dlux-update-image]').click();
    assert.equal(await page.locator('[data-dlux-update-target]').textContent(), 'sha256:9c4b81108b54');
    const baked = page.locator('[data-dlux-update-baked]');
    assert.equal(await baked.isVisible(), true);
    assert.equal(await baked.textContent(), 'baked dlux v1.10.0');
    await closePage();
  });
});

const OPS_STATE = (over = {}) => ({
  operations: OPERATIONS, run: null, check: null, has_preview: false, composer_version: '1.6.0',
  resident: { version: '1.6.0', checked: false, update_available: false }, ...over,
});

const OPS_SCRIPT = `
  const s = window.__server;
  if (url === '/o/run') { s.started = true; return { ok: true, run: { operation: s.operation, status: 'running', active: true } }; }
  if (url === '/o/state') {
    if (s.started && n >= 2) { s.started = false; s.finished = true; return { ...s.state, ...s.after, run: { operation: s.operation, status: 'completed', active: false } }; }
    if (s.started) return { ...s.state, run: { operation: s.operation, status: 'running', active: true } };
    return s.finished ? { ...s.state, ...s.after } : s.state;
  }
  return { ok: true };`;

async function runOps(operation, before, after) {
  const errors = await open('/ops', OPS_SCRIPT, { state: before, after, operation });
  await page.locator(`[data-dlux-ops-check="${operation}"]`).click();
  await page.waitForFunction((name) => window.__server.finished
    && !document.querySelector(`[data-dlux-ops-check="${name}"]`).classList.contains('dlux-btn--loading'), operation, { timeout: 15000 });
  return errors;
}

const glyph = (row) => page.locator(`[data-dlux-ops-glyph="${row}"]`).getAttribute('class');

describe('the resident Composer row through a real check', () => {
  test('a check that finds the pair current ends on a tick', async () => {
    const errors = await runOps('agent-check', OPS_STATE(),
      { resident: { version: '1.6.0', checked: true, update_available: false, published_version: '1.6.0', checked_at: '2026-09-30T10:00:00Z' } });
    assert.match(await glyph('agent-check'), /bi-check-circle-fill/);
    assert.deepEqual(errors, []);
    await closePage();
  });

  test('a check that could not read the registry says so instead of going quiet', async () => {
    await runOps('agent-check', OPS_STATE(),
      { resident: { version: '1.6.0', checked: false, update_available: false, checked_at: '2026-09-30T10:00:00Z',
        detail: 'The published version of debeski/composer:latest could not be read.' } });
    const notice = page.locator('[data-dlux-ops-composer-notice]');
    assert.equal(await notice.isVisible(), true);
    assert.match(await notice.textContent(), /Could not check for a Composer update: The published version of debeski\/composer:latest could not be read\./);
    const icon = await glyph('agent-check');
    assert.doesNotMatch(icon, /bi-check-circle-fill/, 'unknown is not "current"');
    assert.match(icon, /bi-exclamation-triangle/, 'and it is not an invitation to check again as if nothing happened');
    await closePage();
  });
});

const CHECK = (findings, repairs = []) => ({
  operation: 'check', status: 'completed', active: false, error: '', completed_at: '2026-09-30T10:00:00Z',
  findings, repairs,
  summary: { total: findings.length, ok: findings.filter((f) => f.level === 'ok').length,
    warn: findings.filter((f) => f.level === 'warn').length, fail: findings.filter((f) => f.level === 'fail').length },
});
const WARN = { level: 'warn', name: 'versions', message: 'Version drift: deploying composer 1.6.0, resident composer-agent 1.6.0b1.', fix: 'Run ./start.sh agent update' };

describe('the deployment row and its results', () => {
  test('warnings that cannot be repaired show a warning, not the arrow that invites another check', async () => {
    await open('/ops', OPS_SCRIPT, { state: OPS_STATE({ check: CHECK([WARN]), run: CHECK([WARN]), has_preview: true }) });
    const icon = await glyph('check');
    assert.match(icon, /bi-exclamation-triangle/);
    assert.doesNotMatch(icon, /bi-arrow-clockwise/);
    await page.locator('[data-dlux-ops-results]').click();
    const note = page.locator('[data-dlux-ops-norepair]');
    assert.equal(await note.isVisible(), true, 'the modal says plainly that no automatic repair exists');
    assert.equal(await note.textContent(), 'No automatic repair is available for these findings.');
    assert.equal(await page.locator('[data-dlux-ops-offer]').isVisible(), false);
    await closePage();
  });

  test('findings with a repair offer it in the results modal footer, and accepting asks for the password', async () => {
    const repair = [{ name: 'resident-block', files: ['compose.yml'], diff: '+  composer-executor:', note: '' }];
    const fail = { level: 'fail', name: 'resident-block', message: 'composer-executor is not defined.' };
    await open('/ops', OPS_SCRIPT, { state: OPS_STATE({ check: CHECK([fail], repair), run: CHECK([fail], repair), has_preview: true }) });
    await page.locator('[data-dlux-ops-results]').click();
    const offer = page.locator('[data-dlux-ops-offer]');
    assert.equal(await offer.isVisible(), true);
    assert.equal(await page.locator('[data-dlux-ops-norepair]').isVisible(), false);
    assert.equal(await page.locator('[data-dlux-ops-confirm]').isVisible(), false, 'reading is not applying');

    await offer.click();
    assert.equal(await page.locator('[data-dlux-ops-confirm]').isVisible(), true);
    assert.equal(await page.locator('[data-dlux-ops-submit]').textContent(), 'Apply repairs');
    assert.equal(await offer.isVisible(), false);
    await closePage();
  });

  test('a clean check is a tick and offers nothing', async () => {
    const ok = { level: 'ok', name: 'docker', message: 'Docker daemon reachable.' };
    await open('/ops', OPS_SCRIPT, { state: OPS_STATE({ check: CHECK([ok]), run: CHECK([ok]), has_preview: true }) });
    assert.match(await glyph('check'), /bi-check-circle-fill/);
    await page.locator('[data-dlux-ops-results]').click();
    assert.equal(await page.locator('[data-dlux-ops-offer]').isVisible(), false);
    assert.equal(await page.locator('[data-dlux-ops-norepair]').isVisible(), false, 'nothing to repair, nothing to say');
    await closePage();
  });
});

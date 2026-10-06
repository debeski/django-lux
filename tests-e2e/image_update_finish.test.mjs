// An image update's end, from both pages that see it.
//
// Composer writes `ready` before the new web container's DjangoLux has marked the
// update completed and lowered the maintenance flag. The update modal used to
// reload on `ready` and land on the maintenance page; that page only redirected
// if it had seen a progress phase first, so a first read of `ready` left it there
// for good. Here a stub server plays both: the deploy status reaches `ready`
// while the app still answers 503.
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
const MAINTENANCE = path.join(HERE, '..', 'dlux', 'scaffold', 'templates', 'project', '.proxy', 'maintenance.html.tmpl');
const PORT = 8744;
const BASE = `http://localhost:${PORT}`;

const UPDATER = `
<div class="dlux-updater" data-dlux-updater data-can-manage="true" data-state-url="/u/state" data-check-url="/u/check"
     data-image-url="/u/image" data-label-finish="Finish" data-label-last-check="Last check"
     data-label-image-local="Local build" data-label-baked-dlux="baked dlux" data-note-baked-dlux="baked">
  <div class="dlux-upd-row">
    <button type="button" data-dlux-update-check><i class="bi bi-arrow-clockwise" data-dlux-check-glyph></i></button>
    <button type="button" data-dlux-update-review hidden></button>
    <span data-dlux-update-active></span><span data-dlux-update-latest></span>
    <button type="button" data-dlux-update-rollback hidden></button><button type="button" data-dlux-release-notes hidden></button>
  </div>
  <div class="dlux-upd-row">
    <i class="bi bi-check-circle-fill" data-dlux-image-ok></i>
    <button type="button" data-dlux-update-image hidden>update image</button>
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
  <div data-dlux-update-progress-panel hidden>
    <span data-dlux-update-progress-status></span>
    <div data-dlux-update-progress><div class="progress-bar" data-dlux-update-progress-bar></div></div>
    <pre data-dlux-update-progress-log>log of the previous update</pre>
  </div>
  <div data-dlux-update-error hidden></div>
  <button type="button" class="btn btn-secondary" data-bs-dismiss="modal" data-dlux-update-dismiss>Cancel</button>
  <button type="button" data-dlux-update-submit></button>
</div>`;

const PAGE = `<!doctype html><html><head><meta charset="utf-8"><meta name="csrf-token" content="tok"></head>
<body>${UPDATER}<script src="/dlux/helpers/loading_button/js/main.js"></script><script src="/dlux/system/js/updater.js"></script></body></html>`;

const STATE = (over = {}) => ({
  active_version: '1.11.0b2', latest_version: '1.11.0b2', latest_compatible: false, last_checked_at: '2026-10-06T10:00:00Z',
  last_check_error: '', previous_version: '', skipped_versions: [], update_channel: 'beta', can_manage: true,
  image: { image: 'debeski/decrees', app_version: '2.1.20', running_digest: 'sha256:aaaa', checked_at: '', last_update: null },
  image_update_available: true, image_update_target: '2.1.21', ...over,
});

let server;
let browser;
let page;
let loads = {};
let maintenance = { appAnswers: false };

before(async () => {
  const maintenanceHtml = fs.readFileSync(MAINTENANCE, 'utf-8').replaceAll('{{ stack_schema }}', '2');
  server = http.createServer((req, res) => {
    const url = req.url.split('?')[0];
    loads[url] = (loads[url] || 0) + 1;
    if (url === '/updater') { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(PAGE); return; }
    if (url === '/_update/status.json') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      // The modal is opened on a real update: a progress phase, then `ready`. The
      // maintenance page is loaded straight onto `ready`.
      const status = maintenance.appAnswers === null && loads[url] <= 2 ? 'pulling' : 'ready';
      res.end(JSON.stringify({ status, updated_at: '2026-10-06T10:00:00Z' }));
      return;
    }
    if (url === '/_update/log.txt') { res.writeHead(200, { 'Content-Type': 'text/plain' }); res.end('pulled; recreated'); return; }
    if (url === '/records/42/') {
      if (maintenance.appAnswers) { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end('<!doctype html><title>app</title><p id="app">record 42</p>'); return; }
      res.writeHead(503, { 'Content-Type': 'text/html' });
      res.end(maintenanceHtml);
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

// The app API is stubbed in the page so a reply can be a 503 (web recreating or
// still behind maintenance); /_update/* and the page itself come from the server.
async function openUpdater(outcome) {
  loads = {};
  maintenance.appAnswers = null;
  page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  await page.addInitScript(({ state, outcome }) => {
    window.bootstrap = { Modal: class {
      constructor(e) {
        this.e = e;
        document.addEventListener('click', (event) => {
          if (event.target.closest('[data-bs-dismiss="modal"]') && !event.target.disabled) this.hide();
        });
      }
      show() { this.e.dataset.open = 'true'; }
      hide() {
        const veto = new Event('hide.bs.modal', { cancelable: true });
        this.e.dispatchEvent(veto);
        if (veto.defaultPrevented) return;
        this.e.dataset.open = 'false';
        this.e.dispatchEvent(new Event('hidden.bs.modal'));
      }
    } };
    const s = { state, started: false, polls: 0 };
    window.__s = s;
    const realFetch = window.fetch.bind(window);
    const reply = (status, payload) => Promise.resolve({ ok: status < 400, status, json: () => Promise.resolve(payload) });
    window.fetch = (url, options = {}) => {
      const key = String(url);
      if (key.startsWith('/_update/')) return realFetch(url, options);
      if (key === '/u/image') {
        s.started = true;
        return reply(200, { ok: true, image_update: { token: 'img1', status: 'backing_up', active: true, progress_log: 'Creating pre-update backup.' } });
      }
      if (key === '/u/state') {
        if (!s.started) return reply(200, { ok: true, state: s.state, run: null, image_update: null });
        s.polls += 1;
        if (s.polls <= 3) return reply(503, {});
        const last = { token: 'img1', status: outcome, target: '2.1.21', error: outcome === 'failed' ? 'Pull failed.' : '' };
        return reply(200, { ok: true, state: { ...s.state, image: { ...s.state.image, last_update: last } }, run: null, image_update: null });
      }
      return reply(200, { ok: true });
    };
  }, { state: STATE(), outcome });
  await page.goto(`${BASE}/updater`, { waitUntil: 'networkidle' });
  await page.locator('[data-dlux-update-image]').click();
  await page.locator('input[name="current_password"]').fill('pw');
  await page.locator('[data-dlux-update-submit]').click();
  return errors;
}

const dismiss = () => page.locator('[data-dlux-update-dismiss]');

describe('the update modal at the end of an image update', () => {
  test('waits for DjangoLux to report completion, then offers Finish, which reloads', async () => {
    const errors = await openUpdater('completed');
    assert.notEqual(await page.locator('[data-dlux-update-progress-log]').textContent(), 'log of the previous update',
      'the previous update\'s log is cleared when the modal opens');
    assert.equal(await dismiss().isDisabled(), true, 'the modal is locked while the update runs');

    await page.waitForFunction(() => window.__s.polls >= 3, null, { timeout: 20000 });
    assert.equal(loads['/updater'], 1, 'no reload on Composer\'s `ready` while web still answers 503');

    await page.waitForFunction(() => document.querySelector('[data-dlux-update-dismiss]').textContent === 'Finish', null, { timeout: 20000 });
    assert.equal(await dismiss().isDisabled(), false);
    assert.match(await dismiss().getAttribute('class'), /btn-success/);
    assert.equal(loads['/updater'], 1, 'Finish waits for the operator');

    await dismiss().click();
    await page.waitForFunction(() => document.readyState === 'complete' && !window.__s.started, null, { timeout: 10000 });
    assert.equal(loads['/updater'], 2, 'closing after success reloads the page onto the new image');
    assert.deepEqual(errors, []);
    await page.close();
  });

  test('a failed update unlocks the modal without offering Finish or reloading', async () => {
    const errors = await openUpdater('failed');
    await page.waitForFunction(() => window.__s.polls >= 4 && !document.querySelector('[data-dlux-update-dismiss]').disabled, null, { timeout: 25000 });
    assert.equal(await dismiss().textContent(), 'Cancel');
    assert.match(await page.locator('[data-dlux-update-progress-bar]').getAttribute('class'), /bg-danger/);
    await dismiss().click();
    await page.waitForTimeout(500);
    assert.equal(loads['/updater'], 1);
    assert.deepEqual(errors, []);
    await page.close();
  });
});

describe('the maintenance page', () => {
  test('a first read of `ready` returns to the page the visitor was on once the app answers', async () => {
    maintenance.appAnswers = false;
    page = await browser.newPage();
    await page.goto(`${BASE}/records/42/`);
    assert.match(await page.content(), /Update in progress/);
    await page.waitForTimeout(2500);
    assert.equal(page.url(), `${BASE}/records/42/`, 'still waiting while the app answers 503');
    maintenance.appAnswers = true;
    await page.waitForSelector('#app', { timeout: 15000 });
    assert.equal(page.url(), `${BASE}/records/42/`, 'back on the same page, not /');
    await page.close();
  });
});

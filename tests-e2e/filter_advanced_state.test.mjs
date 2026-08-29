// The advanced filter panel must remember whether it was left open.
//
// `advanced_filter_helper` decides the panel's state server-side, from whether
// an advanced field currently holds a value. That covers "a filter is active",
// but not "the user opened the panel" — so opening it and paginating, or just
// reloading, collapsed it again. The behaviour existed in project-dhub as
// hand-written per-template localStorage and was never carried into dlux when
// the helper moved here in v1.0.3.
//
// No dlux page uses the helper (consuming projects do), so this drives the
// shipped filter_form.js against the markup the helper emits, in a real
// browser: class-only assertions would not catch a regression in the
// bootstrap collapse events the persistence hangs off.
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
const PORT = 8731;
const BASE = `http://localhost:${PORT}`;
const PANEL = 'advanced-search';

// Mirrors what advanced_filter_helper renders: the toggle button carries the
// hardcoded `dlux-filter-toggle` class, the panel is `collapse` + the id from
// `advanced_target`. `show` is added by the helper when a filter is active.
const fixture = (shown) => `<!doctype html><html><head><meta charset="utf-8"></head><body>
<form method="get" class="py-3 row g-2 no-print m-0 dlux-form dlux-filter">
  <button class="btn btn-outline-secondary dlux-filter-chip dlux-filter-toggle" type="button"
    data-bs-toggle="collapse" data-bs-target="#${PANEL}"
    aria-expanded="${shown}" aria-controls="${PANEL}">Advanced</button>
  <div id="${PANEL}" class="collapse m-0${shown ? ' show' : ''}"><input name="status"></div>
</form>
<script src="/bootstrap/bootstrap.bundle.min.js"></script>
<script src="/dlux/forms/js/filter_form.js" defer></script>
</body></html>`;

let server;
let browser;
let page;

before(async () => {
  server = http.createServer((req, res) => {
    const url = req.url.split('?')[0];
    if (url === '/list/' || url === '/other/') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      return res.end(fixture(false));
    }
    if (url === '/filtered/') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      return res.end(fixture(true));
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

const state = () => page.evaluate((id) => ({
  shown: document.getElementById(id).classList.contains('show'),
  aria: document.querySelector('.dlux-filter-toggle').getAttribute('aria-expanded'),
  stored: localStorage.getItem(`dluxFilterAdvanced:${location.pathname}#${id}`),
}), PANEL);

const toggle = async (expected) => {
  await page.click('.dlux-filter-toggle');
  await page.waitForFunction(
    ([id, want]) => document.getElementById(id).classList.contains('show') === want,
    [PANEL, expected],
  );
};

describe('advanced filter collapse state', () => {
  test('survives a reload once opened', async () => {
    await page.goto(`${BASE}/list/`);
    assert.equal((await state()).shown, false, 'starts collapsed');

    await toggle(true);
    assert.equal((await state()).stored, 'true');

    await page.reload();
    const after = await state();
    assert.equal(after.shown, true, 'still expanded after reload');
    assert.equal(after.aria, 'true', 'toggle reports expanded');
  });

  test('survives pagination', async () => {
    await page.goto(`${BASE}/list/?page=2`);
    assert.equal((await state()).shown, true);
  });

  test('stays closed once collapsed', async () => {
    await toggle(false);
    await page.reload();
    const after = await state();
    assert.equal(after.shown, false, 'still collapsed after reload');
    assert.equal(after.aria, 'false');
  });

  test('an active advanced filter outranks a stored collapse', async () => {
    // Otherwise a stored "collapsed" hides a filter that is in effect.
    await page.goto(`${BASE}/filtered/`);
    await page.evaluate((id) => localStorage.setItem(
      `dluxFilterAdvanced:${location.pathname}#${id}`, 'false'), PANEL);
    await page.reload();

    const after = await state();
    assert.equal(after.shown, true, 'server-rendered show wins');
    assert.equal(after.stored, 'false', 'stored preference is left untouched');
  });

  test('each list keeps its own state', async () => {
    await page.goto(`${BASE}/other/`);
    assert.equal((await state()).shown, false);
  });
});

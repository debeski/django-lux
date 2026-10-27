// The personal column organizer shows and hides a column with an eye on its
// header, with no inspector: one control, one state, readable at a glance.
//
// Driven against the shipped column strip and organizer scripts, on the
// markup dlux/tables/personal_columns.html renders.
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
const PORT = 8735;
const BASE = `http://localhost:${PORT}`;

const page_html = (dir) => `<!doctype html><html dir="${dir}"><head><meta charset="utf-8"></head><body>
<form method="post" class="dlux-table-columns" data-personal-columns data-default-order='["number","title","date"]'
      data-previous="Move earlier" data-next="Move later" data-show="Show column" data-hide="Hide column"
      data-keep-one="Keep at least one column visible.">
  <input type="hidden" name="preferences" value='{"order":["number","title","date"],"hidden":["title"]}' data-personal-columns-value>
  <div class="dlux-table-columns__headers" data-personal-columns-list>
    <div data-column-name="number" data-column-label="Number" data-column-visible="true">Number</div>
    <div data-column-name="title" data-column-label="Title" data-column-visible="false">Title</div>
    <div data-column-name="date" data-column-label="Date" data-column-visible="true">Date</div>
  </div>
  <button type="button" data-personal-columns-reset>Restore</button>
</form>
<script src="/dlux/helpers/column_strip/js/main.js"></script>
<script src="/dlux/personal_columns/js/main.js"></script>
</body></html>`;

let server;
let browser;
let page;

before(async () => {
  server = http.createServer((req, res) => {
    const url = req.url.split('?')[0];
    if (url === '/ltr.html' || url === '/rtl.html') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      return res.end(page_html(url === '/rtl.html' ? 'rtl' : 'ltr'));
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

const state = () => page.evaluate(() => ({
  value: JSON.parse(document.querySelector('[data-personal-columns-value]').value),
  headers: Array.from(document.querySelectorAll('[data-column-header]')).map((cell) => {
    const eye = cell.querySelector('.dlux-table-columns__eye');
    return {
      name: cell.dataset.columnHeader,
      hidden: cell.classList.contains('is-removed'),
      icon: eye.querySelector('i').className,
      pressed: eye.getAttribute('aria-pressed'),
      label: eye.getAttribute('aria-label'),
      disabled: eye.disabled,
    };
  }),
}));

const eye = (name) => `[data-column-header="${name}"] .dlux-table-columns__eye`;

describe('personal column eyes', () => {
  test('every column gets an eye that shows its current state, and there is no inspector', async () => {
    await page.goto(`${BASE}/ltr.html`);
    const { headers } = await state();
    assert.deepEqual(headers.map((h) => [h.name, h.hidden, h.icon, h.pressed]), [
      ['number', false, 'bi bi-eye', 'false'],
      ['title', true, 'bi bi-eye-slash', 'true'],
      ['date', false, 'bi bi-eye', 'false'],
    ]);
    assert.equal(headers[0].label, 'Hide column: Number');
    assert.equal(headers[1].label, 'Show column: Title');
    assert.equal(await page.locator('.dlux-inspector, [data-personal-column-inspector]').count(), 0);
  });

  test('clicking an eye shows or hides that column and updates what is saved', async () => {
    await page.goto(`${BASE}/ltr.html`);
    await page.click(eye('title'));
    let { value, headers } = await state();
    assert.deepEqual(value.hidden, []);
    assert.equal(headers[1].hidden, false);
    await page.click(eye('date'));
    ({ value, headers } = await state());
    assert.deepEqual(value.hidden, ['date']);
    assert.equal(headers[2].icon, 'bi bi-eye-slash');
    assert.deepEqual(value.order, ['number', 'title', 'date']);
  });

  test('the last shown column cannot be hidden', async () => {
    await page.goto(`${BASE}/ltr.html`);
    await page.click(eye('date'));
    const { value, headers } = await state();
    assert.deepEqual(value.hidden, ['date', 'title']);
    const number = headers.find((h) => h.name === 'number');
    assert.equal(number.disabled, true);
    assert.equal(await page.getAttribute(eye('number'), 'title'), 'Keep at least one column visible.');
  });

  test('Restore shows every column in the default order', async () => {
    await page.goto(`${BASE}/ltr.html`);
    await page.click(`[data-column-header="date"] [data-column-move="-1"]`);
    await page.click('[data-personal-columns-reset]');
    const { value, headers } = await state();
    assert.deepEqual(value, { order: ['number', 'title', 'date'], hidden: [] });
    assert.ok(headers.every((h) => !h.hidden && h.icon === 'bi bi-eye'));
  });

  test('the eye works the same in RTL', async () => {
    await page.goto(`${BASE}/rtl.html`);
    await page.click(eye('number'));
    const { value } = await state();
    assert.deepEqual(value.hidden, ['number', 'title']);
  });
});

// The admin panel's one arrow.
//
// System info and Updates and maintenance each keep half of themselves out of
// the way — a details table and the update settings — and a single unlabelled
// arrow at the foot of the update card opens both. Both, because the cards
// stretch to a common height: opening one alone would only add empty space to
// the other.
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

const PAGE = `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/dlux/system/css/options.css"></head>
<body>
<div class="dlux-admin-panel-top">
  <section class="dlux-admin-tile dlux-admin-tile--status">
    <h5 class="dlux-admin-tile-title">System info</h5>
    <div class="dlux-admin-more" id="dlux-admin-more-system" data-dlux-more>
      <table class="dlux-options-system-info-table"><tr><th>OS:</th><td>Linux</td></tr></table>
    </div>
  </section>
  <section class="dlux-admin-tile dlux-admin-tile--update">
    <h5 class="dlux-admin-tile-title">Updates and maintenance</h5>
    <div class="dlux-updater-rows"><div class="dlux-upd-row"><span class="dlux-upd-name">DjangoLux</span></div></div>
    <div class="dlux-admin-more" id="dlux-admin-more-updates" data-dlux-update-settings data-dlux-more>
      <input type="range" id="dlux-update-check-interval" data-dlux-interval-range>
    </div>
    <button type="button" class="dlux-admin-expand" data-dlux-expand
            aria-expanded="false" aria-controls="dlux-admin-more-system dlux-admin-more-updates"
            aria-label="Show details and settings"><i class="bi bi-chevron-down"></i></button>
  </section>
</div>
<script src="/dlux/system/js/options.js"></script>
</body></html>`;

let server;
let browser;
let page;

// `is-open` is what turns the chevron over and what drives the reveal; the
// computed transform is read mid-animation and would report a closing arrow as
// still rotated. `visibility` is what keeps a closed panel out of the tab order
// and off a screen reader, and it flips only once the fold has finished.
const state = () => page.evaluate(() => ({
  expanded: document.querySelector('[data-dlux-expand]').getAttribute('aria-expanded'),
  open: Array.from(document.querySelectorAll('[data-dlux-more]')).map((el) => el.classList.contains('is-open')),
  visible: Array.from(document.querySelectorAll('[data-dlux-more]')).map(
    (el) => getComputedStyle(el).visibility === 'visible'),
  rotated: document.querySelector('[data-dlux-expand]').classList.contains('is-open'),
}));

const settled = (visible) => page.waitForFunction(
  (want) => Array.from(document.querySelectorAll('[data-dlux-more]')).every(
    (el) => (getComputedStyle(el).visibility === 'visible') === want),
  visible,
);

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
    const type = file.endsWith('.css') ? 'text/css' : 'application/javascript';
    res.writeHead(200, { 'Content-Type': type });
    res.end(fs.readFileSync(file));
  });
  await new Promise((resolve) => server.listen(PORT, resolve));
  browser = await chromium.launch();
  page = await browser.newPage();
  await page.goto(BASE, { waitUntil: 'networkidle' });
});

after(async () => {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
});

describe('the admin panel arrow', () => {
  test('there is exactly one, and it carries no text', async () => {
    assert.equal(await page.locator('[data-dlux-expand]').count(), 1,
      'System info has no arrow of its own');
    assert.equal((await page.locator('[data-dlux-expand]').textContent()).trim(), '');
    assert.equal(await page.locator('[data-dlux-expand]').getAttribute('aria-label'),
      'Show details and settings', 'no visible label, but a screen reader still gets one');
  });

  test('both halves start hidden', async () => {
    assert.deepEqual(await state(),
      { expanded: 'false', open: [false, false], visible: [false, false], rotated: false });
  });

  test('one click opens both cards, a second closes both', async () => {
    await page.locator('[data-dlux-expand]').click();
    await settled(true);
    assert.deepEqual(await state(),
      { expanded: 'true', open: [true, true], visible: [true, true], rotated: true });

    await page.locator('[data-dlux-expand]').click();
    await settled(false);
    assert.deepEqual(await state(),
      { expanded: 'false', open: [false, false], visible: [false, false], rotated: false });
  });

  test('closing changes the card\'s height by interpolation alone', async () => {
    // A flex gap survives a zero-height child, so taking the panel out of the
    // layout at the end of the fold cost the card those pixels in one frame.
    // That was the flicker; sampling the card itself is what would catch it.
    const card = () => page.evaluate(() => Math.round(
      document.querySelector('[data-dlux-expand]').closest('.dlux-admin-tile')
        .getBoundingClientRect().height));

    const closed = await card();
    await page.locator('[data-dlux-expand]').click();
    await settled(true);
    await page.waitForTimeout(300);
    const open = await card();
    assert.ok(open > closed, 'opening should make the card taller');

    await page.locator('[data-dlux-expand]').click();
    await settled(false);
    const landed = await card();
    await page.waitForTimeout(150);
    assert.equal(await card(), landed,
      'the card must not lose height after the fold has finished');
    assert.equal(landed, closed, 'and it must land exactly where it started');
  });

  test('it grows and shrinks rather than appearing', async () => {
    const heights = [];
    const sample = () => page.evaluate(() => Math.round(
      document.querySelector('[data-dlux-more]').getBoundingClientRect().height));

    await page.locator('[data-dlux-expand]').click();
    await page.waitForTimeout(60);
    heights.push(await sample());
    await settled(true);
    await page.waitForTimeout(260);
    const full = await sample();
    assert.ok(heights[0] < full, `mid-open ${heights[0]}px should be short of ${full}px`);
    assert.ok(heights[0] > 0, 'it should already be on its way, not waiting to appear');

    await page.locator('[data-dlux-expand]').click();
    await page.waitForTimeout(60);
    const closing = await sample();
    assert.ok(closing < full && closing > 0, `mid-close ${closing}px should be shrinking, not gone`);
    await settled(false);
  });

  test('it sits at the card\'s end, on the side the language reads towards', async () => {
    const side = async (dir) => {
      await page.evaluate((d) => { document.documentElement.dir = d; }, dir);
      return page.evaluate(() => {
        const button = document.querySelector('[data-dlux-expand]');
        const icon = button.querySelector('.bi');
        const b = button.getBoundingClientRect();
        const i = icon.getBoundingClientRect();
        return { start: Math.round(i.left - b.left), end: Math.round(b.right - i.right) };
      });
    };
    const ltr = await side('ltr');
    assert.ok(ltr.end <= 2 && ltr.start > 100, `not at the right in LTR: ${JSON.stringify(ltr)}`);
    const rtl = await side('rtl');
    assert.ok(rtl.start <= 2 && rtl.end > 100, `not at the left in RTL: ${JSON.stringify(rtl)}`);
    await page.evaluate(() => { document.documentElement.removeAttribute('dir'); });
  });

  test('it sits at the very bottom of the card it lives in', async () => {
    assert.equal(await page.evaluate(() => {
      const card = document.querySelector('[data-dlux-expand]').closest('.dlux-admin-tile');
      return card.lastElementChild.dataset.dluxExpand !== undefined;
    }), true, 'the arrow must be the last thing in the card');
  });
});

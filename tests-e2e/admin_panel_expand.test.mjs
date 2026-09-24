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
    <div class="dlux-admin-more" id="dlux-admin-more-system" data-dlux-more hidden>
      <table class="dlux-options-system-info-table"><tr><th>OS:</th><td>Linux</td></tr></table>
    </div>
  </section>
  <section class="dlux-admin-tile dlux-admin-tile--update">
    <h5 class="dlux-admin-tile-title">Updates and maintenance</h5>
    <div class="dlux-updater-rows"><div class="dlux-upd-row"><span class="dlux-upd-name">DjangoLux</span></div></div>
    <div class="dlux-admin-more" id="dlux-admin-more-updates" data-dlux-update-settings data-dlux-more hidden>
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

// `is-open` is what turns the chevron over; the computed transform is read
// mid-animation and would report a closing arrow as still rotated.
const state = () => page.evaluate(() => ({
  expanded: document.querySelector('[data-dlux-expand]').getAttribute('aria-expanded'),
  hidden: Array.from(document.querySelectorAll('[data-dlux-more]')).map((el) => el.hidden),
  rotated: document.querySelector('[data-dlux-expand]').classList.contains('is-open'),
}));

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
    assert.deepEqual(await state(), { expanded: 'false', hidden: [true, true], rotated: false });
  });

  test('one click opens both cards, a second closes both', async () => {
    await page.locator('[data-dlux-expand]').click();
    assert.deepEqual(await state(), { expanded: 'true', hidden: [false, false], rotated: true });

    await page.locator('[data-dlux-expand]').click();
    assert.deepEqual(await state(), { expanded: 'false', hidden: [true, true], rotated: false });
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

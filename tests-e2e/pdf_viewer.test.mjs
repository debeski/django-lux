// The record PDF viewer (dlux/pdf/viewer.html + pdf/js/viewer.js).
//
// Two bugs found on testbed-dlux before 1.13.0: zoom did nothing (the canvas
// was capped at `max-width: 100%`, so a page already wider than the modal
// column was drawn larger and shrunk straight back), and the fullscreen button
// could enter fullscreen but not leave it.
//
// Real pdf.js, the real template and stylesheet, a two-page PDF fixture, in a
// column as narrow as the detail modal's.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..');
const STATIC = path.join(ROOT, 'dlux', 'static');
const PY = path.join(ROOT, '.venv', 'bin', 'python');
const PORT = 8745;
const BASE = `http://localhost:${PORT}`;

const VIEWER = execFileSync(PY, ['-c', `
import django; django.setup()
from types import SimpleNamespace
from django.template.loader import render_to_string
print(render_to_string('dlux/pdf/viewer.html', {
    'source_url': '/fixtures/two-pages.pdf', 'download_url': '/fixtures/two-pages.pdf', 'file_name': 'two-pages.pdf',
    'pdf_features': {'editing_enabled': False, 'history_enabled': False},
    'request': SimpleNamespace(csp_nonce='n'),
}))
`], { cwd: ROOT, env: { ...process.env, DJANGO_SETTINGS_MODULE: 'dlux.tests.settings', PYTHONPATH: ROOT } }).toString();

const page_html = (withPdfJs) => `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/bootstrap/bootstrap.min.css">
<link rel="stylesheet" href="/static/bootstrap/bootstrap-icons.css">
<link rel="stylesheet" href="/static/dlux/pdf/css/main.css">
<style>.column { width: 520px; margin: 20px; }</style>
</head><body><div class="column">${VIEWER}</div>
${withPdfJs ? '<script src="/static/dlux/pdf/vendor/pdf.min.js"></script>' : ''}
<script src="/static/dlux/pdf/js/viewer.js"></script>
</body></html>`;

let server;
let browser;
let page;

before(async () => {
  server = http.createServer((req, res) => {
    const url = req.url.split('?')[0];
    if (url === '/' || url === '/fallback') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(page_html(url === '/'));
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
  await new Promise((resolve) => server.listen(PORT, resolve));
  browser = await chromium.launch();
});

after(async () => {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
});

async function open(route = '/') {
  await page?.close();
  page = await browser.newPage({ viewport: { width: 1000, height: 800 }, deviceScaleFactor: 2 });
  await page.goto(BASE + route, { waitUntil: 'networkidle' });
}

const zoomOf = () => page.evaluate(() => Number(document.querySelector('.dlux-pdf-viewer').dataset.pdfZoom || 0));
const waitZoom = (value) => page.waitForFunction(
  (v) => Number(document.querySelector('.dlux-pdf-viewer').dataset.pdfZoom) === v, value, { timeout: 5000 });
// fullscreenElement changes a moment before `fullscreenchange` reaches the viewer.
const pressed = (value) => page.waitForFunction(
  (v) => document.querySelector('[data-pdf-fullscreen]').getAttribute('aria-pressed') === v, value, { timeout: 5000 });
const geometry = () => page.evaluate(() => {
  const stage = document.querySelector('.dlux-pdf-stage');
  const canvas = stage.querySelector('canvas');
  const styles = getComputedStyle(stage);
  return {
    canvas: canvas.getBoundingClientRect().width,
    inner: stage.clientWidth - parseFloat(styles.paddingLeft) - parseFloat(styles.paddingRight),
    pixels: canvas.width,
  };
});

describe('zoom', () => {
  test('the page opens fitted to the column, drawn at the screen density', async () => {
    await open();
    await waitZoom(1);
    const g = await geometry();
    assert.ok(Math.abs(g.canvas - g.inner) <= 2, `fits the width (${g.canvas} vs ${g.inner})`);
    assert.ok(Math.abs(g.pixels - g.canvas * 2) <= 4, 'twice the pixels on a 2x screen, so it stays sharp');
    assert.equal(await page.locator('[data-pdf-canvas]').evaluate((el) => getComputedStyle(el).direction), 'ltr',
      'an RTL page must not mirror the PDF text');
  });

  test('zooming in and out changes the size on screen', async () => {
    await open();
    await waitZoom(1);
    const fitted = (await geometry()).canvas;
    await page.locator('[data-pdf-zoom-in]').click();
    await waitZoom(1.25);
    assert.ok(Math.abs((await geometry()).canvas - fitted * 1.25) <= 2, 'zoom in enlarges the page');
    await page.locator('[data-pdf-zoom-out]').click();
    await page.locator('[data-pdf-zoom-out]').click();
    await waitZoom(0.75);
    assert.ok(Math.abs((await geometry()).canvas - fitted * 0.75) <= 2, 'zoom out shrinks it below the fit');
  });

  test('quick clicks are all counted, not dropped while a page draws', async () => {
    await open();
    await waitZoom(1);
    const zoomIn = page.locator('[data-pdf-zoom-in]');
    await zoomIn.click();
    await zoomIn.click();
    await zoomIn.click();
    await waitZoom(1.75);
  });

  test('a zoomed page scrolls to its start edge', async () => {
    await open();
    await waitZoom(1);
    await page.locator('[data-pdf-zoom-in]').click();
    await page.locator('[data-pdf-zoom-in]').click();
    await waitZoom(1.5);
    const reachable = await page.evaluate(() => {
      const stage = document.querySelector('.dlux-pdf-stage');
      stage.scrollLeft = 0;
      return stage.querySelector('canvas').getBoundingClientRect().left >= stage.getBoundingClientRect().left;
    });
    assert.equal(reachable, true, 'centring an overflowing page used to cut its left edge off');
  });

  test('the buttons stop at the limits', async () => {
    await open();
    await waitZoom(1);
    const zoomOut = page.locator('[data-pdf-zoom-out]');
    await zoomOut.click();
    await zoomOut.click();
    await waitZoom(0.5);
    assert.equal(await zoomOut.isDisabled(), true);
  });
});

describe('fullscreen', () => {
  test('the button enters and leaves fullscreen and says which it will do', async () => {
    await open();
    await waitZoom(1);
    const button = page.locator('[data-pdf-fullscreen]');
    assert.equal(await button.getAttribute('title'), 'Fullscreen');
    await button.click();
    await page.waitForFunction(() => document.fullscreenElement?.classList.contains('dlux-pdf-viewer'));
    await pressed('true');
    assert.equal(await button.locator('i').getAttribute('class'), 'bi bi-fullscreen-exit');
    assert.equal(await button.getAttribute('title'), 'Exit fullscreen');
    assert.equal(await button.getAttribute('aria-pressed'), 'true');
    const fills = await page.evaluate(() => document.querySelector('.dlux-pdf-stage').getBoundingClientRect().height > innerHeight * 0.8);
    assert.equal(fills, true, 'the page area takes the screen');

    await button.click();
    await page.waitForFunction(() => !document.fullscreenElement);
    await pressed('false');
    assert.equal(await button.locator('i').getAttribute('class'), 'bi bi-arrows-fullscreen');
  });

  test('leaving fullscreen another way (Esc) resets the button too', async () => {
    await open();
    await waitZoom(1);
    const button = page.locator('[data-pdf-fullscreen]');
    await button.click();
    await page.waitForFunction(() => Boolean(document.fullscreenElement));
    await pressed('true');
    await page.evaluate(() => document.exitFullscreen());
    await pressed('false');
    assert.equal(await button.getAttribute('title'), 'Fullscreen');
  });
});

describe('without pdf.js', () => {
  test('the browser shows the file; page and zoom controls are off, fullscreen still works', async () => {
    await open('/fallback');
    assert.equal(await page.locator('.dlux-pdf-viewer').evaluate((el) => el.classList.contains('is-fallback')), true);
    assert.equal(await page.locator('[data-pdf-zoom-in]').isDisabled(), true);
    assert.equal(await page.locator('[data-pdf-next]').isDisabled(), true);
    await page.locator('[data-pdf-fullscreen]').click();
    await page.waitForFunction(() => Boolean(document.fullscreenElement));
  });
});

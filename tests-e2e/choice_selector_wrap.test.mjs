// Card choice selectors size their columns from the widest option and spread
// them across the whole row. Driven on the real Extra Features editor, whose
// "Models included in automatic OCR" list is a searchable multi-select card
// selector; urls.py registers six file models when DLUX_E2E_OCR_MODELS is set.

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { startServer, chromium, BASE } from './server.mjs';
import { CREDENTIALS } from './routes.mjs';

const SHOTS = fileURLToPath(new URL('./shots/', import.meta.url));
const SELECTOR = '#id_ocr_automatic_models';
// The card variant's --dlux-choice-option-width default (12rem at a 16px root).
const PRESET = 192;

let server, browser;
before(async () => {
  server = await startServer({ ocrModels: true });
  browser = await chromium.launch();
}, { timeout: 120000 });
after(async () => { if (browser) await browser.close(); if (server) await server.stop(); });

async function openExtras(width, { arabic = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width, height: 1000 } });
  const page = await ctx.newPage();
  page.setDefaultTimeout(10000);
  const errors = [];
  page.on('pageerror', (error) => errors.push(String(error)));
  page.on('console', (message) => { if (message.type() === 'error') errors.push(`console: ${message.text()}`); });
  await page.goto(`${BASE}/accounts/login/`);
  await page.fill('[name="username"]', CREDENTIALS.username);
  await page.fill('[name="password"]', CREDENTIALS.password);
  await Promise.all([page.waitForURL((url) => !url.pathname.includes('/login/')), page.click('button[type="submit"]')]);
  await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
  if (arabic) {
    const status = await page.evaluate(async () => {
      const csrf = document.querySelector('meta[name="csrf-token"]')?.content || '';
      const response = await fetch('/sys/api/preferences/update/', {
        method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
        body: JSON.stringify({ language: 'ar' }),
      });
      return response.status;
    });
    assert.equal(status, 200);
    await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
  }
  await page.locator('[data-dlux-settings-step="extras"]').click();
  await page.locator(SELECTOR).waitFor({ state: 'visible' });
  await page.waitForFunction((sel) => document.querySelector(sel)?.style.getPropertyValue('--dlux-choice-option-fit'), SELECTOR);
  return { ctx, page, errors };
}

function measure(page) {
  return page.locator(SELECTOR).evaluate((selector) => {
    const grid = selector.querySelector('[data-dlux-selector-options]');
    const style = getComputedStyle(grid);
    const columns = style.gridTemplateColumns.split(' ').map(parseFloat).filter((width) => width > 0);
    const options = [...grid.querySelectorAll('[data-dlux-selector-option]')].filter((option) => option.style.display !== 'none');
    return {
      fit: parseFloat(selector.style.getPropertyValue('--dlux-choice-option-fit')),
      columns,
      gap: parseFloat(style.columnGap),
      gridWidth: grid.getBoundingClientRect().width,
      count: options.length,
      widths: options.map((option) => option.querySelector('.dlux-choice-option__surface').getBoundingClientRect().width),
      clipped: options.filter((option) => {
        const label = option.querySelector('.dlux-choice-option__label');
        return label.scrollWidth > label.clientWidth + 1;
      }).length,
    };
  });
}

for (const width of [1440, 820, 390]) {
  test(`card columns follow the widest option and fill the row at ${width}px`, async () => {
    const { ctx, page, errors } = await openExtras(width);
    try {
      const m = await measure(page);
      assert.equal(m.count, 6);
      assert.equal(m.clipped, 0, 'no option label is cut off');
      const track = Math.min(m.gridWidth, PRESET, m.fit);
      const fits = Math.floor((m.gridWidth + m.gap) / (track + m.gap));
      assert.equal(m.columns.length, Math.max(1, Math.min(m.count, fits)), JSON.stringify(m));
      const used = m.columns.reduce((sum, column) => sum + column, 0) + m.gap * (m.columns.length - 1);
      assert.ok(Math.abs(used - m.gridWidth) <= 1, `columns span the row: ${JSON.stringify(m)}`);
      assert.ok(Math.min(...m.columns) >= track - 1, `no column is narrower than the widest option: ${JSON.stringify(m)}`);
      // Every option fills its column, so they all share one width.
      assert.ok(m.widths.every((w) => Math.abs(w - m.columns[0]) <= 1), `options fill their columns: ${JSON.stringify(m)}`);

      // Filtering keeps the columns: the widest option still counts while hidden.
      await page.locator(`${SELECTOR} [data-dlux-selector-search]`).fill('pap');
      await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const filtered = await measure(page);
      assert.equal(filtered.fit, m.fit);
      assert.equal(filtered.count, 1);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
}

test('Arabic Extra Features under the light and dark themes', async () => {
  const { ctx, page, errors } = await openExtras(1440, { arabic: true });
  try {
    assert.equal(await page.evaluate(() => document.documentElement.dir), 'rtl');
    // One option off, so both the checked and the unchecked surface show.
    await page.locator(`${SELECTOR} .dlux-choice-option__input`).nth(1).uncheck({ force: true });
    for (const theme of ['light', 'dark']) {
      await page.evaluate(async (name) => {
        await window.dluxLoadThemeStylesheet(name);
        const root = document.documentElement;
        [...root.classList].filter((c) => c.startsWith('theme-')).forEach((c) => root.classList.remove(c));
        root.classList.add(`theme-${name}`);
      }, theme);
      await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
      const m = await measure(page);
      assert.equal(m.clipped, 0);
      await page.locator('#div_id_ocr_automatic_models').screenshot({ path: `${SHOTS}choice-selector-ocr-models-ar-${theme}.png` });
    }
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

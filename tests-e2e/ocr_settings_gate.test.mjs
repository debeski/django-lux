// OCR's options wait on Enable OCR, like every other dependent section: greyed
// out with the shared tooltip naming the switch while it is off, live again as
// soon as it is on. The password and the Operations panel stay usable.

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { startServer, chromium, BASE } from './server.mjs';
import { CREDENTIALS } from './routes.mjs';

const SHOTS = fileURLToPath(new URL('./shots/', import.meta.url));

let server, browser;
before(async () => {
  server = await startServer();
  browser = await chromium.launch();
}, { timeout: 120000 });
after(async () => { if (browser) await browser.close(); if (server) await server.stop(); });

async function openExtras({ arabic = false } = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
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
  await page.locator('[data-ocr-dependent]').waitFor({ state: 'visible' });
  return { ctx, page, errors };
}

function state(page) {
  return page.evaluate(() => {
    const dependent = document.querySelector('[data-ocr-dependent]');
    const controls = [...dependent.querySelectorAll('input, select, textarea, button')].filter((c) => c.type !== 'hidden');
    const label = document.querySelector('[data-dlux-settings-toggle-field="ocr_enabled"] .dlux-settings-toggle-field__label');
    return {
      greyed: dependent.classList.contains('is-disabled'),
      disabled: controls.filter((c) => c.disabled).length,
      total: controls.length,
      tooltip: dependent.getAttribute('data-dlux-tooltip') || '',
      switchName: label ? label.textContent.trim() : '',
      password: document.querySelector('[name="ocr_current_password"]').disabled,
    };
  });
}

test('OCR options are greyed out with a tooltip until Enable OCR is on', async () => {
  const { ctx, page, errors } = await openExtras();
  try {
    const off = await state(page);
    assert.equal(off.greyed, true);
    assert.equal(off.disabled, off.total, JSON.stringify(off));
    assert.ok(off.total >= 10, JSON.stringify(off));
    assert.ok(off.switchName && off.tooltip.includes(off.switchName), JSON.stringify(off));
    assert.equal(off.password, false, 'the password stays usable');
    await page.locator('[data-ocr-dependent]').scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${SHOTS}ocr-settings-off.png` });

    const enable = page.locator('[name="ocr_enabled"]');
    await enable.check({ force: true });
    const on = await state(page);
    assert.equal(on.greyed, false);
    assert.equal(on.disabled, 0, JSON.stringify(on));
    assert.equal(on.tooltip, '');
    await page.screenshot({ path: `${SHOTS}ocr-settings-on.png` });

    await enable.uncheck({ force: true });
    const again = await state(page);
    assert.equal(again.greyed, true);
    assert.equal(again.disabled, again.total);
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

test('Arabic: the tooltip names the Arabic switch', async () => {
  const { ctx, page, errors } = await openExtras({ arabic: true });
  try {
    const off = await state(page);
    assert.equal(off.greyed, true);
    assert.ok(off.switchName && off.tooltip.includes(off.switchName), JSON.stringify(off));
    const toggle = page.locator('[data-ocr-dependent] [data-dlux-settings-toggle-field="ocr_auto_on_save"]');
    await toggle.scrollIntoViewIfNeeded();
    await toggle.hover();
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${SHOTS}ocr-settings-off-ar-tooltip.png` });
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

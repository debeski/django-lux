// System Settings previews in the first-run setup wizard.
//
// The wizard is a page of its own, so there is nothing to lift a modal off:
// Preview and every section eye open the popup, which renders a real page with
// the wizard's unsaved values. Nothing is saved — the system stays unconfigured.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, openWizard, chromium, BASE } from './server.mjs';

let server;
let browser;

before(async () => {
  server = await startServer({ configured: false });
  browser = await chromium.launch();
}, { timeout: 120000 });

after(async () => {
  if (browser) await browser.close();
  if (server) await server.stop();
});

async function wizard() {
  const { ctx, page, errors } = await loggedInPage(browser);
  await openWizard(page);
  return { ctx, page, errors };
}

async function setField(page, name, value) {
  await page.evaluate(([n, v]) => {
    const el = document.querySelector(`.dlux-system-setup-form [name="${n}"]`);
    if (!el) throw new Error(`field ${n} not found`);
    el.value = v;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }, [name, value]);
}

async function popupFrame(page) {
  await page.waitForSelector('.dlux-preview-popup iframe[src*="_dlux_preview="]', { timeout: 20000 });
  await page.waitForFunction(() => document.querySelector('.dlux-preview-popup__status')?.hidden === true, null, { timeout: 20000 });
  return (await page.$('.dlux-preview-popup iframe')).contentFrame();
}

describe('wizard previews', { concurrency: 1 }, () => {
  test('the wizard never uses glass mode: Preview opens the popup', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const modes = await page.$$eval('[data-dlux-system-settings-preview]', (buttons) => buttons.map((b) => b.dataset.previewMode));
      assert.ok(modes.length > 0);
      assert.ok(!modes.includes('glass'));
      assert.equal(await page.$('.dlux-preview-backdrop'), null, 'no live backdrop on the wizard');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the first-run setup page has no global footer', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      assert.equal(await page.$('footer.dlux-footer'), null);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a preview renders a real page with the unsaved wizard values', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await page.evaluate(() => {
        const toggle = document.querySelector('.dlux-system-setup-form [name="footer_enabled"]');
        if (toggle && !toggle.checked) toggle.click();
      });
      await setField(page, 'footer_text', 'Wizard draft footer');
      await page.evaluate(() => window.DluxSetupPreview.openPreview(document.querySelector('.dlux-system-setup-form'), 'sample_components'));
      const frame = await popupFrame(page);
      const footer = await frame.$eval('footer.dlux-footer', (el) => el.textContent);
      assert.match(footer, /Wizard draft footer/);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the login eye renders the real login page, and the system stays unconfigured', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await page.evaluate(() => window.DluxSetupPreview.openPreview(document.querySelector('.dlux-system-setup-form'), 'login'));
      const frame = await popupFrame(page);
      assert.ok(await frame.$('input[name="password"]'));
      await page.goto(`${BASE}/sys/setup/`, { waitUntil: 'networkidle' });
      assert.ok(await page.$('.dlux-system-setup-form, form[action*="setup"], .dlux-setup-page'), 'still the setup wizard: nothing was saved');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

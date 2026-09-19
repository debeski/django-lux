import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';

let server;
let browser;

before(async () => {
  server = await startServer({ configured: true });
  browser = await chromium.launch();
}, { timeout: 120000 });

after(async () => {
  if (browser) await browser.close();
  if (server) await server.stop();
});

async function optionsStep(step) {
  const { ctx, page, errors } = await loggedInPage(browser);
  await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
  await page.click(`.dlux-system-settings-tile[data-dynamic-modal*="?step=${step}"]`);
  await page.waitForSelector('#universalDynamicModal.show .dlux-system-setup-form');
  return { ctx, page, errors };
}

describe('Options System Settings previews', { concurrency: 1 }, () => {
  test('titlebar fields update the rendered titlebar through the preview namespace', async () => {
    const { ctx, page, errors } = await optionsStep(5);
    try {
      const result = await page.evaluate(() => {
        const form = document.querySelector('#universalDynamicModal .dlux-system-setup-form');
        const field = form.querySelector('[name="titlebar_show_title"]');
        field.checked = false;
        field.dispatchEvent(new Event('change', { bubbles: true }));
        return {
          namespace: typeof window.DluxSetupPreview?.applyTitlebarPreview,
          state: document.querySelector('.titlebar')?.dataset.titlebarShowTitle,
        };
      });
      assert.equal(result.namespace, 'function');
      assert.equal(result.state, 'false');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('sidebar fields update real Options chrome and remain no-op safe elsewhere', async () => {
    const { ctx, page, errors } = await optionsStep(6);
    try {
      const result = await page.evaluate(() => {
        const form = document.querySelector('#universalDynamicModal .dlux-system-setup-form');
        const field = form.querySelector('[name="sidebar_enabled"]');
        field.checked = false;
        field.dispatchEvent(new Event('change', { bubbles: true }));
        const sidebar = document.getElementById('sidebar');
        return {
          enabled: sidebar?.dataset.sidebarEnabled,
          display: sidebar?.style.display,
        };
      });
      assert.equal(result.enabled, 'false');
      assert.equal(result.display, 'none');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('persistent notification settings do not mutate live notification chrome', async () => {
    const { ctx, page, errors } = await optionsStep(14);
    try {
      const result = await page.evaluate(() => {
        const roots = Array.from(document.querySelectorAll('[data-dlux-notifications]'));
        const before = roots.map((node) => ({
          enabled: node.dataset.dluxNotificationsEnabled,
          badge: node.dataset.badgeEnabled,
          display: node.style.display,
        }));
        const form = document.querySelector('#universalDynamicModal .dlux-system-setup-form');
        const field = form.querySelector('[name="notifications_enabled"]');
        field.checked = !field.checked;
        field.dispatchEvent(new Event('change', { bubbles: true }));
        const after = roots.map((node) => ({
          enabled: node.dataset.dluxNotificationsEnabled,
          badge: node.dataset.badgeEnabled,
          display: node.style.display,
        }));
        return { before, after };
      });
      assert.deepEqual(result.after, result.before);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

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
  test('non-visual steps expose a clearly disabled Preview action', async () => {
    const { ctx, page, errors } = await optionsStep(2);
    try {
      const state = await page.$eval(
        '#universalDynamicModalFooter [data-dlux-system-settings-preview]',
        (button) => ({
          disabled: button.disabled,
          mode: button.dataset.previewMode,
          step: button.dataset.previewStep,
          title: button.title,
        }),
      );
      assert.equal(state.disabled, true);
      assert.equal(state.mode, '');
      assert.equal(state.step, 'email');
      assert.match(state.title, /not available/i);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

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

  test('glass preview restores repeatedly and consumes the exit click before save', async () => {
    const { ctx, page, errors } = await optionsStep(5);
    try {
      const preview = '#universalDynamicModalFooter [data-dlux-system-settings-preview]';
      const save = '#universalDynamicModalFooter button[type="submit"]';
      const field = '#universalDynamicModal [name="titlebar_show_title"]';
      const initial = await page.isChecked(field);
      await page.locator(field).setChecked(!initial);

      const mode = await page.$eval(preview, (button) => button.dataset.previewMode);
      assert.equal(mode, 'glass');
      await page.click(preview);
      await page.waitForSelector('#universalDynamicModal.dlux-system-preview-glass');
      const hiddenChrome = await page.$eval(
        '#universalDynamicModal .modal-content > *',
        (element) => getComputedStyle(element).opacity,
      );
      assert.equal(hiddenChrome, '0');

      await page.keyboard.press('Escape');
      await page.waitForSelector('#universalDynamicModal.dlux-system-preview-glass', { state: 'detached' });
      await page.locator(field).setChecked(initial);
      await page.click(preview);
      await page.waitForSelector('#universalDynamicModal.dlux-system-preview-glass');

      await page.evaluate(() => {
        const tile = document.querySelector('.dlux-system-settings-tile');
        window.__dluxPreviewUnderlyingClicks = 0;
        tile.addEventListener('click', () => { window.__dluxPreviewUnderlyingClicks += 1; });
      });
      const box = await page.locator('#universalDynamicModal .modal-content').boundingBox();
      await page.mouse.click(box.x + (box.width / 2), box.y + (box.height / 2));
      await page.waitForSelector('#universalDynamicModal.dlux-system-preview-glass', { state: 'detached' });
      assert.equal(await page.evaluate(() => window.__dluxPreviewUnderlyingClicks), 0);

      await page.click(save);
      await page.waitForSelector('#universalDynamicModal.show', { state: 'detached' });
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('popup preview renders unsaved login values and preserves them across cycles', async () => {
    const { ctx, page, errors } = await optionsStep(11);
    try {
      const preview = '#universalDynamicModalFooter [data-dlux-system-settings-preview]';
      const field = '#universalDynamicModal.show [name^="login_hero_message_"]';
      await page.evaluate(() => {
        document.querySelectorAll('#universalDynamicModal.show [name^="login_hero_message_"]').forEach((input) => {
          input.value = 'Unsaved preview marker';
          input.dispatchEvent(new Event('input', { bubbles: true }));
        });
      });
      assert.equal(await page.$eval(preview, (button) => button.dataset.previewMode), 'popup');

      for (const closeKey of ['Escape', 'q']) {
        await page.click(preview);
        await page.waitForSelector('[data-dlux-system-preview-popup]');
        assert.match(
          await page.textContent('[data-dlux-system-preview-popup]'),
          /Unsaved preview marker/,
        );
        await page.keyboard.press(closeKey);
        await page.waitForSelector('[data-dlux-system-preview-popup]', { state: 'detached' });
        assert.equal(await page.$eval(field, (input) => input.value), 'Unsaved preview marker');
      }
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

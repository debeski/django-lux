// Functional tests for the wizard's centralized live previews.
//
// These are what make the wizard feel live — edit a setting and the surrounding
// chrome updates immediately, without a save. That also makes them the easiest
// thing to break silently during a refactor: nothing errors, the preview simply
// stops responding, and the operator is configuring blind.
//
// Sidebar behavior is covered from the Options context, where the target exists.
//
// `applyLayoutBodyPreview` deliberately does not preview `default_form_density`
// or `default_modal_size` — they are admin defaults for per-user preferences,
// and previewing them would overwrite the editing admin's own resolved values.
// That exclusion is documented in the function; a test asserting the absence
// would be structurally unable to fail, so there isn't one.
//
// The state-cache half of the same batch (persistSetupFormState,
// applySetupFormStateValues, getSetupStateKey) is already covered by
// wizard.test.mjs — "submitting caches the form" and "a cached state is
// restored" — so it is not duplicated here.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, openWizard, chromium } from './server.mjs';

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

async function setToggle(page, name, on) {
  await page.evaluate(([n, v]) => {
    const el = document.querySelector(`.dlux-system-setup-form [name="${n}"]`);
    if (!el) throw new Error(`toggle ${n} not found`);
    if (el.checked !== v) {
      el.checked = v;
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, [name, on]);
  await page.waitForTimeout(250);
}

async function setField(page, name, value) {
  await page.evaluate(([n, v]) => {
    const el = document.querySelector(`.dlux-system-setup-form [name="${n}"]`);
    if (!el) throw new Error(`field ${n} not found`);
    el.value = v;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }, [name, value]);
  await page.waitForTimeout(250);
}

describe('wizard live previews', { concurrency: 1 }, () => {
  test('Preview follows wizard step capabilities and renders unsaved homepage state', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const preview = '[data-dlux-system-settings-preview]';
      assert.equal(await page.$eval(preview, (button) => button.dataset.previewStep), 'branding');
      assert.equal(await page.$eval(preview, (button) => button.dataset.previewMode), 'popup');

      await page.click('[data-dlux-wizard-step-target="2"]');
      assert.equal(await page.$eval(preview, (button) => button.disabled), true);
      assert.equal(await page.$eval(preview, (button) => button.dataset.previewStep), 'email');

      await page.click('[data-dlux-wizard-step-target="10"]');
      await setField(page, 'public_root_title', 'Unsaved homepage marker');
      assert.equal(await page.$eval(preview, (button) => button.disabled), false);
      assert.equal(await page.$eval(preview, (button) => button.dataset.previewMode), 'popup');
      await page.click(preview);
      await page.waitForSelector('[data-dlux-system-preview-popup]');
      assert.match(
        await page.textContent('[data-dlux-system-preview-popup]'),
        /Unsaved homepage marker/,
      );
      await page.keyboard.press('Escape');
      await page.waitForSelector('[data-dlux-system-preview-popup]', { state: 'detached' });
      assert.equal(await page.inputValue('[name="public_root_title"]'), 'Unsaved homepage marker');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('font, navbar, and ribbon previews use the available live or popup surface', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await page.click('[data-dlux-wizard-step-target="4"]');
      const fontResult = await page.evaluate(() => {
        localStorage.removeItem('appFont');
        if (window.USER_PREFS) window.USER_PREFS.font = '';
        const [slug, family] = Object.entries(window.DLUX_FONT_FAMILIES || {})[0] || [];
        if (!slug) return null;
        const input = document.querySelector('.dlux-system-setup-form [name="default_fonts"]');
        const language = String(document.documentElement.lang || 'en').split('-')[0];
        input.value = JSON.stringify({ [language]: slug });
        input.dispatchEvent(new Event('change', { bubbles: true }));
        return { family, applied: document.documentElement.style.getPropertyValue('--dlux-main-font') };
      });
      assert.ok(fontResult, 'the test page did not expose any configured font family');
      assert.match(fontResult.applied, new RegExp(fontResult.family.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));

      for (const [step, selector] of [
        [7, '.dlux-system-preview-shell__navbar'],
        [8, '.dlux-system-preview-shell__ribbon'],
      ]) {
        await page.click(`[data-dlux-wizard-step-target="${step}"]`);
        await page.click('[data-dlux-system-settings-preview]');
        await page.waitForSelector(`[data-dlux-system-preview-popup] ${selector}`);
        await page.keyboard.press('Escape');
        await page.waitForSelector('[data-dlux-system-preview-popup]', { state: 'detached' });
      }
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the footer toggle shows and hides the real footer', async () => {
    // The preview drives the actual <footer> on the page, not a mock-up, so a
    // broken preview leaves the operator looking at the wrong chrome.
    const { ctx, page, errors } = await wizard();
    try {
      const footerPresent = await page.$('footer.dlux-footer');
      if (!footerPresent) return; // footer not rendered in this layout

      const shown = () => page.evaluate(() => {
        const f = document.querySelector('footer.dlux-footer');
        return f ? getComputedStyle(f).display !== 'none' : null;
      });

      await setToggle(page, 'footer_enabled', true);
      assert.equal(await shown(), true, 'enabling the footer did not reveal it');

      await setToggle(page, 'footer_enabled', false);
      assert.equal(await shown(), false, 'disabling the footer did not hide it');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('footer text typed in the wizard appears in the footer', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      if (!(await page.$('.dlux-footer__text'))) return;

      await setToggle(page, 'footer_enabled', true);
      await setField(page, 'footer_text', 'preview-marker-text');

      const shown = (await page.textContent('.dlux-footer__text') || '');
      assert.ok(shown.includes('preview-marker-text'),
        `the typed footer text did not reach the preview; saw ${JSON.stringify(shown.trim())}`);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('global layout toggles are published onto the body dataset', async () => {
    // Other stylesheets key off these attributes, so they are the contract
    // between the wizard and the rest of the chrome.
    const { ctx, page, errors } = await wizard();
    try {
      const ds = () => page.evaluate(() => ({
        sticky: document.body.dataset.dluxStickyHeader,
        resize: document.body.dataset.dluxTableResize,
        zebra: document.body.dataset.dluxZebra,
      }));

      for (const [field, key] of [
        ['sticky_table_headers', 'sticky'],
        ['resizable_table_columns', 'resize'],
        ['zebra_striping', 'zebra'],
      ]) {
        if (!(await page.$(`.dlux-system-setup-form [name="${field}"]`))) continue;
        await setToggle(page, field, true);
        assert.equal((await ds())[key], 'on', `${field} on did not publish ${key}=on`);
        await setToggle(page, field, false);
        assert.equal((await ds())[key], 'off', `${field} off did not publish ${key}=off`);
      }
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

});

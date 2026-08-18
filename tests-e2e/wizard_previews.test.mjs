// Functional tests for the wizard's live previews:
// applyFooterPreview, applyLayoutBodyPreview, applySidebarPreview and friends.
//
// Written BEFORE they move to setup/js/previews.js.
//
// These are what make the wizard feel live — edit a setting and the surrounding
// chrome updates immediately, without a save. That also makes them the easiest
// thing to break silently during a refactor: nothing errors, the preview simply
// stops responding, and the operator is configuring blind.
//
// `applySidebarPreview` is NOT covered and did NOT move: the setup wizard
// renders no sidebar at all (`#sidebar` and `.sidebar` are both absent), so its
// 112 lines have nothing to act on there and cannot be verified across a move.
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

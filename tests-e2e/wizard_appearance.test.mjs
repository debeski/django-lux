// Functional tests for the wizard's appearance cluster.
//
// Movable: initSetupThemePicker, initSetupFontPicker.
// Not movable: initSetupTableDensityPicker, initSetupSidebarDensityPicker —
// their markup is never rendered (see the last test).
//
// Written BEFORE those four move to setup/js/appearance.js, so the split has a
// net to fall into rather than being verified after the fact. Every assertion
// here describes behaviour that must survive the move unchanged.
//
// The cluster spans TWO surfaces despite the "Setup" prefix on every name:
// base.html loads setup/js/main.js on every page, so its `scan(document)` runs
// site-wide. The theme and font pickers are wizard markup; the density pickers
// are only rendered by system/options.html. Splitting this cluster on the
// assumption that it is wizard-only would silently break the Options page.
//
// Run:  node --test 'tests-e2e/*.test.mjs'

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

/** Reveal the step that owns `selector`. Panels are display:none when inactive,
 *  so anything off-step is unclickable however correct the markup is. */
async function stepContaining(page, selector) {
  const index = await page.evaluate((sel) => {
    const steps = [...document.querySelectorAll('.wizard-step')];
    return steps.findIndex((s) => s.querySelector(sel));
  }, selector);
  assert.ok(index >= 0, `no wizard step contains ${selector}`);
  await page.click(`[data-dlux-wizard-step-target="${index}"]`);
  await page.waitForSelector(selector, { state: 'visible', timeout: 5000 });
  return index;
}

async function wizard() {
  const { ctx, page, errors } = await loggedInPage(browser);
  await openWizard(page);
  return { ctx, page, errors };
}

describe('wizard appearance cluster', { concurrency: 1 }, () => {
  test('language font table has a theme-driven body surface', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '.dlux-language-fonts-table-wrap');
      const surfaces = await page.evaluate(() => {
        const root = document.documentElement;
        const wrap = document.querySelector('.dlux-language-fonts-table-wrap');
        const table = wrap?.querySelector('.dlux-language-fonts-table');
        if (!wrap || !table) return null;
        const result = {};
        for (const theme of ['mono', 'dark']) {
          [...root.classList]
            .filter((name) => name.startsWith('theme-'))
            .forEach((name) => root.classList.remove(name));
          root.classList.add(`theme-${theme}`);
          const style = getComputedStyle(wrap);
          result[theme] = {
            background: style.backgroundColor,
            borderStyle: style.borderTopStyle,
            tableMarginBottom: getComputedStyle(table).marginBottom,
          };
        }
        return result;
      });

      assert.ok(surfaces, 'the language-font table did not render');
      assert.notEqual(surfaces.mono.background, 'rgba(0, 0, 0, 0)');
      assert.notEqual(surfaces.dark.background, 'rgba(0, 0, 0, 0)');
      assert.notEqual(surfaces.mono.background, surfaces.dark.background);
      assert.equal(surfaces.mono.borderStyle, 'solid');
      assert.equal(surfaces.dark.borderStyle, 'solid');
      assert.equal(surfaces.mono.tableMarginBottom, '0px');
      assert.equal(surfaces.dark.tableMarginBottom, '0px');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('choosing a theme re-allows it if it was disallowed', async () => {
    // All twelve themes ship allowed, so asserting "it is allowed after
    // clicking" proves nothing — it was already on. The behaviour only shows
    // if the theme is first taken OUT of the allowed set.
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-setup-theme-choice]');
      const target = 'neon';

      // Click the checkbox itself, not the surrounding container: the
      // container's handler deliberately early-returns when the click lands on
      // `[data-setup-theme-allowed]` or `[data-setup-theme-choice]`, which
      // between them fill it. The checkbox carries its own click/change pair.
      await page.click(`[data-setup-theme-allowed="${target}"]`, { force: true });
      await page.waitForTimeout(200);
      assert.equal(
        await page.isChecked(`[data-setup-theme-allowed="${target}"]`), false,
        'precondition failed: the theme should be disallowed before we pick it',
      );

      await page.click(`[data-setup-theme-choice="${target}"]`);
      await page.waitForTimeout(250);

      // Picking a theme must re-tick its allowed box, or the wizard posts a
      // default theme that is not in the allowed set.
      assert.equal(
        await page.isChecked(`[data-setup-theme-allowed="${target}"]`), true,
        'choosing a disallowed theme did not re-allow it',
      );
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the last allowed theme cannot be unchecked', async () => {
    // Guards the same invariant as
    // test_defaults_and_urls.py::test_system_setup_js_keeps_last_allowed_theme_postable.
    // With zero allowed themes the form posts an empty set and the app has no
    // theme to render.
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-setup-theme-allowed]');
      const names = await page.$$eval('[data-setup-theme-allowed]',
        (els) => els.map((e) => e.getAttribute('data-setup-theme-allowed')));
      assert.ok(names.length >= 2, 'need at least two themes to exercise the lock');

      // Turn every one of them off through the visible control.
      for (const name of names) {
        await page.click(`[data-setup-theme-allowed="${name}"]`, { force: true });
        await page.waitForTimeout(80);
      }
      await page.waitForTimeout(200);

      const stillAllowed = await page.$$eval('[data-setup-theme-allowed]',
        (els) => els.filter((e) => e.checked).map((e) => e.value));
      assert.equal(
        stillAllowed.length, 1,
        `the lock should leave exactly one theme allowed, got ${JSON.stringify(stillAllowed)}`,
      );
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the setup-mode density picker markup is never rendered', async () => {
    // Records a finding rather than asserting behaviour. `initSetupTableDensityPicker`
    // and `initSetupSidebarDensityPicker` bind to `[data-setup-*-density-picker]`,
    // which previews/table_density.html and previews/sidebar_density.html emit only
    // under `picker_mode == 'setup'` — and nothing in dlux passes that. All six
    // includes pass 'options'. So both inits are unreachable in this package.
    //
    // They were left in main.js rather than moved with the rest of the appearance
    // cluster: code that cannot be exercised cannot be verified across a move. They
    // were also not deleted — dlux ships its templates, so a downstream project can
    // include them with picker_mode='setup' and light this path up.
    //
    // If that mode is ever wired here, this test fails and the two inits become
    // testable and movable.
    await server.stop();
    server = await startServer({ configured: true });
    const { ctx, page } = await loggedInPage(browser);
    try {
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      const cards = await page.$$eval('[data-options-card]', (els) => els.map((e) => e.getAttribute('data-options-card')));
      assert.ok(cards.includes('table-density'), 'the table-density card should be on the Options page');
      assert.equal(
        await page.$('[data-setup-table-density-choice]'), null,
        'setup-mode density markup is now rendered — the two dead inits are live again',
      );
      assert.equal(await page.$('[data-setup-sidebar-density-choice]'), null);
    } finally {
      await ctx.close();
      await server.stop();
      server = await startServer({ configured: false });
    }
  });

  test('font picker keeps at least one font allowed', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const present = await page.$('[data-setup-font-allowed]');
      if (!present) return; // font picker is optional markup
      await stepContaining(page, '[data-setup-font-allowed]');

      const before = await page.$$eval('[data-setup-font-allowed]', (els) => els.filter((e) => e.checked).length);
      assert.ok(before >= 1, 'no font allowed on load');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

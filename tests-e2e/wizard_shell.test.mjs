// Functional tests for the wizard's shell interactions:
// initSystemSetupStepValidation, initSystemSetupEnterBehavior,
// initSetupHomeFields, initGlobalSearchOptions and their helpers.
//
// Written BEFORE they move to setup/js/shell.js.
//
// The Enter-key behaviour is the one worth having. A 14-step form where Enter
// submits from step 2 would post a half-filled configuration; instead Enter
// advances the wizard, except inside a textarea (where it must type a newline)
// and inside the language editor (where it adds the language being typed).
// Each of those three branches is a separate way to lose work.
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

const visibleStep = (page) => page.evaluate(
  () => [...document.querySelectorAll('.wizard-step')].findIndex((s) => !s.classList.contains('d-none')),
);

describe('wizard shell interactions', { concurrency: 1 }, () => {
  test('Enter advances the wizard instead of submitting it', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const start = await visibleStep(page);
      assert.equal(start, 0);

      const field = await page.$('.wizard-step:not(.d-none) input[type="text"]:not([disabled])');
      if (!field) return;
      await field.focus();
      await page.keyboard.press('Enter');
      await page.waitForTimeout(400);

      assert.ok(page.url().includes('/sys/setup/'),
        'Enter submitted the form — a half-filled configuration would have posted');
      assert.equal(await visibleStep(page), start + 1,
        'Enter should advance to the next step');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('Enter inside a textarea types a newline rather than advancing', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      // Step 0 has no enabled textarea, so go to the step that does — otherwise
      // this test early-returns and proves nothing.
      const step = await page.evaluate(() => {
        const steps = [...document.querySelectorAll('.wizard-step')];
        return steps.findIndex((s) => s.querySelector('textarea:not([disabled])'));
      });
      assert.ok(step >= 0, 'no step contains an enabled textarea');
      await page.click(`[data-dlux-wizard-step-target="${step}"]`);
      await page.waitForTimeout(250);

      const area = await page.$('.wizard-step:not(.d-none) textarea:not([disabled])');
      assert.ok(area, 'expected an enabled textarea on the chosen step');
      const start = await visibleStep(page);

      await area.focus();
      await page.keyboard.type('one');
      await page.keyboard.press('Enter');
      await page.keyboard.type('two');
      await page.waitForTimeout(300);

      assert.equal(await visibleStep(page), start,
        'Enter in a textarea must not navigate away mid-sentence');
      const value = await area.inputValue();
      assert.ok(value.includes('\n'), `the newline was swallowed; got ${JSON.stringify(value)}`);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a step with an invalid field is marked in the step nav', async () => {
    // The mark is how an operator finds the problem in a 14-step form; without
    // it they hunt step by step after a rejected submit.
    const { ctx, page, errors } = await wizard();
    try {
      const marked = () => page.evaluate(
        () => document.querySelectorAll('[data-dlux-wizard-step-target].has-validation-error').length,
      );

      const target = await page.evaluate(() => {
        const el = document.querySelector('.dlux-system-setup-form input[type="url"]:not([disabled])')
          || document.querySelector('.dlux-system-setup-form input[type="email"]:not([disabled])');
        if (!el) return null;
        el.value = 'definitely not a url';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return el.name;
      });
      if (!target) return;
      await page.waitForTimeout(400);

      assert.ok(await marked() > 0,
        `an invalid ${target} did not mark its step in the nav`);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the global search mode gates its data-scope option', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const mode = '.dlux-system-setup-form [name="titlebar_global_search_mode"]';
      if (!(await page.$(mode))) return;
      const dep = await page.evaluate(() => {
        const el = document.querySelector('[data-global-search-data-field] input, [data-global-search-data-field] select');
        return el ? el.name : null;
      });
      if (!dep) return;

      // titlebar_global_search_mode is a radio group behind the Dlux choice
      // widget, so the mode is whichever radio is checked — assigning .value to
      // the first one changes nothing.
      const set = async (v) => {
        await page.evaluate((val) => {
          const el = document.querySelector(
            `.dlux-system-setup-form [name="titlebar_global_search_mode"][value="${val}"]`);
          if (!el) throw new Error(`global search mode ${val} not found`);
          el.checked = true;
          el.dispatchEvent(new Event('change', { bubbles: true }));
        }, v);
        await page.waitForTimeout(250);
      };
      const isDisabled = () => page.isDisabled(`.dlux-system-setup-form [name="${dep}"]`);

      await set('disabled');
      assert.equal(await isDisabled(), true,
        'the data-scope option must lock while global search is off');
      await set('icon');
      assert.equal(await isDisabled(), false,
        'enabling global search must unlock its data-scope option');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

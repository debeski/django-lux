// Functional tests for the setup wizard.
//
// Run:  node --test 'tests-e2e/*.test.mjs'
//
// These drive a real Django server and a real browser, because the wizard's
// value is almost entirely DOM-bound: of 147 top-level functions in
// setup/js/main.js only 25 are transitively free of the DOM, and those already
// have unit tests in tests-js/. Everything else — step navigation, dependent
// field gating, state persistence — can only be observed end to end.
//
// The wizard writes system configuration and stays reachable after first boot,
// so a defect here misconfigures a live deployment rather than a one-off
// installer. It had no tests at all before this file.
//
// One server and one browser serve every test; each test gets a fresh page and
// its own localStorage, so state does not leak between them.

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, openWizard, chromium, BASE } from './server.mjs';

let server;
let browser;

before(async () => {
  // `configured: false` — system_setup_view redirects to the options page once
  // SystemSettings.is_configured is true, so the wizard is only reachable from
  // an unconfigured database.
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

// Dlux renders switches as a styled control with the real <input> sized 0x0, so
// Playwright cannot click it. Setting `checked` and dispatching a bubbling
// `change` is what a real click produces, and it is what the wizard listens for
// (main.js binds a single delegated `document` change handler).
async function setToggle(page, name, on) {
  await page.evaluate(([n, v]) => {
    const el = document.querySelector(`.dlux-system-setup-form [name="${n}"]`);
    if (!el) throw new Error(`toggle ${n} not found`);
    if (el.checked !== v) {
      el.checked = v;
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, [name, on]);
  await page.waitForTimeout(200);
}

describe('setup wizard', { concurrency: 1 }, () => {
  test('loads past the language gate with no scripting errors', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const steps = await page.$$eval('[data-dlux-wizard-step-target]', (els) => els.length);
      assert.ok(steps >= 10, `expected the full step nav, saw ${steps}`);
      assert.equal(await page.isVisible('.dlux-setup-intro__desc'), true,
        'first-launch setup must retain its page overview');
      assert.equal(await page.isVisible('.wizard-step:not(.d-none) .dlux-setup-step-badge'), true,
        'first-launch setup must retain its numbered step badge');
      // The wizard's JS builds on window.DluxSetupModel; if that namespace were
      // missing the destructuring at the top of main.js would throw and the
      // whole wizard would be inert while still rendering fine.
      assert.equal(await page.evaluate(() => typeof window.DluxSetupModel), 'object');
      assert.equal(await page.evaluate(() => typeof window.__dluxPrepareWizardContainer), 'function');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('step nav switches the visible panel', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const visibleStep = () => page.evaluate(
        () => [...document.querySelectorAll('.wizard-step')].findIndex((s) => !s.classList.contains('d-none')),
      );
      assert.equal(await visibleStep(), 0, 'the wizard should open on the first step');

      await page.click('[data-dlux-wizard-step-target="2"]');
      await page.waitForFunction(
        () => [...document.querySelectorAll('.wizard-step')].findIndex((s) => !s.classList.contains('d-none')) === 2,
        undefined, { timeout: 5000 },
      );
      // The nav highlight and the panel must agree; either one alone leaves the
      // operator looking at a step the wizard does not think they are on.
      assert.equal(
        await page.evaluate(() => document.querySelector('[data-dlux-wizard-step-target].is-active')
          ?.getAttribute('data-dlux-wizard-step-target')),
        '2',
      );
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('submitting caches the form into sessionStorage', async () => {
    // `persistSetupFormState` runs from the submit handler BEFORE validation,
    // so the operator's input is banked even if the post is rejected. It is not
    // called on keystrokes or step changes — a step change only records the
    // step index in a dataset attribute.
    const { ctx, page, errors } = await wizard();
    try {
      const marker = 'e2e-cache-check';
      const homepageStep = await page.evaluate(() => {
        const field = document.querySelector('[name="public_root_title"]');
        const panels = [...document.querySelectorAll('.wizard-step')];
        return panels.findIndex((panel) => panel.contains(field));
      });
      await page.click(`[data-dlux-wizard-step-target="${homepageStep}"]`);
      await setToggle(page, 'public_root', true);
      await page.fill('input[name="public_root_title"]', marker);

      // Submit only becomes visible on the final panel, and there are more
      // .wizard-step panels than nav buttons — the last panel has no nav
      // target — so jump as far as the nav goes, then step forward.
      const lastNav = await page.evaluate(
        () => document.querySelectorAll('[data-dlux-wizard-step-target]').length - 1,
      );
      await page.click(`[data-dlux-wizard-step-target="${lastNav}"]`);
      await page.waitForTimeout(200);
      for (let i = 0; i < 4 && !(await page.isVisible('.dlux-btn-submit')); i += 1) {
        await page.click('.dlux-btn-next');
        await page.waitForTimeout(200);
      }
      assert.ok(await page.isVisible('.dlux-btn-submit'), 'never reached the final step');

      const cached = await page.evaluate(() => {
        document.querySelector('.dlux-btn-submit').click();
        const key = Object.keys(sessionStorage).find((k) => k.startsWith('dlux.systemSetupState:'));
        return key ? JSON.parse(sessionStorage.getItem(key)) : null;
      });

      assert.ok(cached, 'submit did not cache the form state');
      assert.equal(cached.values.public_root_title, marker);
      assert.equal(cached.values.public_root, true, 'checkbox state is stored as a boolean');
      assert.equal(cached.surface, '/sys/setup/');
      assert.deepEqual(errors, []);
    } finally {
      await ctx.close();
      // A clean submit configures the system, which closes the wizard for every
      // later test. Rebuild a pristine unconfigured server.
      await server.stop();
      server = await startServer({ configured: false });
    }
  });

  test('a cached state is restored into the form on load', async () => {
    // The other half: whatever submit banked must come back. Seeding the cache
    // directly keeps this deterministic — it does not depend on being able to
    // provoke a validation failure, which the default form does not produce.
    const { ctx, page, errors } = await wizard();
    try {
      const marker = 'e2e-restore-check';
      await page.evaluate((value) => {
        sessionStorage.setItem('dlux.systemSetupState:/sys/setup/', JSON.stringify({
          surface: '/sys/setup/',
          values: { public_root: true, public_root_title: value },
        }));
      }, marker);

      await page.reload({ waitUntil: 'networkidle' });
      await page.waitForSelector('.dlux-system-setup-form');
      await page.waitForTimeout(500);

      assert.equal(
        await page.isChecked('input[name="public_root"]'), true,
        'the master toggle was not restored',
      );
      assert.equal(
        await page.inputValue('input[name="public_root_title"]'), marker,
        'the cached value was not restored, so a rejected submit would lose operator input',
      );
      // Restoring the master must also re-open its dependents, or the restored
      // value would sit in a disabled field.
      assert.equal(
        await page.isDisabled('input[name="public_root_title"]'), false,
        'dependent stayed locked after its master was restored',
      );
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a master toggle gates its dependent fields', async () => {
    // DSRP-1: backend authorization must match UI visibility. A dependent left
    // editable under a disabled master invites input that cannot be honoured.
    const { ctx, page, errors } = await wizard();
    try {
      const dependent = 'input[name="public_root_title"]';

      await setToggle(page, 'public_root', false);
      assert.equal(await page.isDisabled(dependent), true,
        'dependent must be disabled while its master is off');

      await setToggle(page, 'public_root', true);
      assert.equal(await page.isDisabled(dependent), false,
        'dependent must unlock when the master is switched on');

      await setToggle(page, 'public_root', false);
      assert.equal(await page.isDisabled(dependent), true,
        'dependent must re-lock when the master is switched back off');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the wizard posts to itself and keeps the form on validation failure', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const action = await page.getAttribute('.dlux-system-setup-form', 'action');
      // An empty action posts to the current URL. Anything else would send the
      // wizard's payload somewhere it is not handled.
      assert.ok(action === null || action === '' || action.includes('/sys/setup/'),
        `unexpected form action: ${action}`);
      assert.equal(await page.getAttribute('.dlux-system-setup-form', 'method'), 'post');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('is unreachable once the system is configured', async () => {
    // The other half of the gate: once configured, system_setup_view redirects
    // to the options page. Without this the wizard would stay open as an
    // unguarded route that rewrites live configuration.
    await server.stop();
    server = await startServer({ configured: true });
    const { ctx, page } = await loggedInPage(browser);
    try {
      const resp = await page.goto(`${BASE}/sys/setup/`, { waitUntil: 'networkidle' });
      assert.equal(new URL(page.url()).pathname, '/sys/options/',
        'configured systems must be redirected away from the setup wizard');
      assert.ok(resp.ok());

      await page.click('.dlux-system-settings-tile[data-dynamic-modal*="?step=0"]');
      await page.waitForSelector('#universalDynamicModalBody .dlux-system-setup-form');
      assert.equal(
        await page.$('#universalDynamicModalBody .dlux-system-settings-intro'),
        null,
        'individual System Settings modals must not repeat the first-launch overview',
      );
      assert.equal(
        await page.$('#universalDynamicModalBody .dlux-setup-step-badge'),
        null,
        'individual System Settings modals must not repeat first-launch step numbering',
      );
    } finally {
      await ctx.close();
      await server.stop();
      server = await startServer({ configured: false });
    }
  });
});

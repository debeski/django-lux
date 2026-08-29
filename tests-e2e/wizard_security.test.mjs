// Functional tests for the wizard's security & access cluster:
// initPublicRegistrationOptions, initPublicPageOptions, initClientIpOptions,
// initAuthSecurityOptions, initLoginPageOptions.
//
// Written BEFORE those five move to setup/js/security.js.
//
// This cluster matters more than its 181 lines suggest. DSRP-1 says backend
// authorization must match UI visibility, and this cluster *is* that UI: it
// decides which security controls an operator can edit. A dependent left
// editable under a disabled master invites input the backend will not honour;
// one wrongly locked hides a control the operator needs.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { startServer, loggedInPage, openWizard, chromium } from './server.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));

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

// Dlux switches render the real <input> at 0x0 behind a styled control, so a
// click cannot reach them. Setting `checked` and dispatching a bubbling
// `change` is what a real click produces and what the wizard listens for.
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

/** Reveal the step owning `selector`. Inactive panels are display:none, so
 *  anything off-step is unclickable however correct the markup is — `setToggle`
 *  and `isDisabled` do not care, but `selectOption` and visibility checks do. */
async function stepContaining(page, selector) {
  const index = await page.evaluate((sel) => {
    const steps = [...document.querySelectorAll('.wizard-step')];
    return steps.findIndex((s) => s.querySelector(sel));
  }, selector);
  assert.ok(index >= 0, `no wizard step contains ${selector}`);
  await page.click(`[data-dlux-wizard-step-target="${index}"]`);
  await page.waitForSelector(selector, { state: 'visible', timeout: 5000 });
}

const disabled = (page, name) => page.isDisabled(`.dlux-system-setup-form [name="${name}"]`);

/** A master must gate every one of its dependents, in both directions. Testing
 *  only the "off" half would pass against a control that is permanently locked. */
async function assertGates(page, master, dependents) {
  await setToggle(page, master, true);
  for (const d of dependents) {
    assert.equal(await disabled(page, d), false, `${d} should be editable while ${master} is on`);
  }
  await setToggle(page, master, false);
  for (const d of dependents) {
    assert.equal(await disabled(page, d), true, `${d} must be locked while ${master} is off`);
  }
  await setToggle(page, master, true);
  for (const d of dependents) {
    assert.equal(await disabled(page, d), false, `${d} must unlock when ${master} is switched back on`);
  }
}

describe('wizard security cluster', { concurrency: 1 }, () => {
  test('asset-picker uploads persist immediately and reach later setup steps', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const upload = page.locator('[name="logo_upload"]');
      await upload.setInputFiles(path.join(HERE, '..', 'dlux', 'static', 'favicon.ico'));
      await page.waitForFunction(() => Boolean(document.querySelector('[name="logo_asset"]')?.value));

      const uploaded = await page.evaluate(() => {
        const id = document.querySelector('[name="logo_asset"]')?.value || '';
        const loginOption = document.querySelector(
          `[name="login_logo_asset"] + input + input + [data-asset-picker-library] [data-asset-id="${id}"]`
        );
        return {
          id,
          pendingFiles: document.querySelector('[name="logo_upload"]')?.files.length,
          loginHasAsset: Boolean(loginOption),
        };
      });
      assert.ok(uploaded.id, 'the immediate upload did not select a managed asset');
      assert.equal(uploaded.pendingFiles, 0, 'the saved asset remained a pending form upload');
      assert.equal(uploaded.loginHasAsset, true, 'the Login picker did not receive the new asset');

      await openWizard(page);
      const persisted = await page.locator(
        `[name="login_logo_asset"] + input + input + [data-asset-picker-library] [data-asset-id="${uploaded.id}"]`
      ).count();
      assert.equal(persisted, 1, 'the asset disappeared after reloading unsaved setup');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('untouched optional file widgets do not mark Identity or Login invalid', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const states = await page.evaluate(() => {
        const steps = [...document.querySelectorAll('.wizard-step')];
        return ['logo_upload', 'login_logo_upload'].map((name) => {
          const input = document.querySelector(`[name="${name}"]`);
          const step = input && input.closest('.wizard-step');
          const index = step ? steps.indexOf(step) : -1;
          const nav = document.querySelector(`[data-dlux-wizard-step-target="${index}"]`);
          return {
            name,
            found: Boolean(input && step && nav),
            required: Boolean(input && input.required),
            valid: Boolean(input && input.checkValidity()),
            warning: Boolean(nav && nav.classList.contains('has-validation-error')),
            invalidControls: step ? [...step.querySelectorAll('input, select, textarea')]
              .filter((control) => typeof control.checkValidity === 'function' && !control.checkValidity())
              .map((control) => ({ name: control.name, type: control.type, required: control.required })) : [],
          };
        });
      });

      for (const state of states) {
        assert.equal(state.found, true, `${state.name} setup control is missing`);
        assert.equal(state.required, false, `${state.name} should be optional`);
        assert.equal(state.valid, true, `${state.name} should be valid while untouched`);
        assert.equal(state.warning, false,
          `${state.name} step should not show a warning: ${JSON.stringify(state.invalidControls)}`);
      }
      const visibleErrorIsRetained = await page.evaluate(() => {
        const form = document.querySelector('.dlux-system-setup-form');
        const input = form.querySelector('[name="logo_upload"]');
        const step = input.closest('.wizard-step');
        const index = [...form.querySelectorAll('.wizard-step')].indexOf(step);
        const error = document.createElement('div');
        error.className = 'invalid-feedback';
        error.textContent = 'Server validation error';
        step.appendChild(error);
        window.DluxSetupDom.updateSetupStepValidationState(form);
        return document.querySelector(`[data-dlux-wizard-step-target="${index}"]`)
          .classList.contains('has-validation-error');
      });
      assert.equal(visibleErrorIsRetained, true, 'a visible server error must still mark its step');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('public page gates its title, description and split option', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await page.evaluate(() => {
        const form = document.querySelector('.dlux-system-setup-form');
        window.DluxSetupDom.setNamedFieldDisabled(form, 'public_root_theme', true);
      });
      await assertGates(page, 'public_root', [
        'public_root_title',
        'public_root_meta_description',
        'public_root_split_enabled',
      ]);
      const enabledAppearance = await page.evaluate(() => {
        const block = document.querySelector('[data-public-page-dependent]');
        const themeSelector = document.querySelector('[name="public_root_theme"]')
          ?.closest('[data-dlux-selector]');
        return {
          disabledClass: block?.classList.contains('is-disabled'),
          opacity: block ? getComputedStyle(block).opacity : null,
          themeDisabledClass: themeSelector?.classList.contains('is-disabled'),
          themeAriaDisabled: themeSelector?.getAttribute('aria-disabled'),
        };
      });
      assert.deepEqual(enabledAppearance, {
        disabledClass: false,
        opacity: '1',
        themeDisabledClass: false,
        themeAriaDisabled: 'false',
      },
        'editable public page fields must also lose their disabled appearance');

      await setToggle(page, 'public_root', false);
      const disabledAppearance = await page.evaluate(() => {
        const block = document.querySelector('[data-public-page-dependent]');
        return {
          disabledClass: block?.classList.contains('is-disabled'),
          opacity: block ? getComputedStyle(block).opacity : null,
        };
      });
      assert.equal(disabledAppearance.disabledClass, true);
      assert.notEqual(disabledAppearance.opacity, '1');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('registration toggle gates throttle and activation mode', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const present = await page.$('.dlux-system-setup-form [name="public_registration_enabled"]');
      assert.ok(present, 'registration master control missing');
      await assertGates(page, 'public_registration_enabled', [
        'registration_throttle_enabled',
        'registration_activation_mode',
      ]);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('login lockout and inactivity timeout each gate only their own fields', async () => {
    // Two independent masters in one step. Switching one must not disturb the
    // other's fields — a shared handler that gates by section rather than by
    // master would pass a single-master test and fail this one.
    const { ctx, page, errors } = await wizard();
    try {
      await setToggle(page, 'login_lockout_enabled', true);
      await setToggle(page, 'inactivity_timeout_enabled', true);

      await setToggle(page, 'login_lockout_enabled', false);
      assert.equal(await disabled(page, 'inactivity_timeout_minutes'), false,
        'disabling lockout must not lock the inactivity fields');

      await setToggle(page, 'inactivity_timeout_enabled', false);
      assert.equal(await disabled(page, 'inactivity_timeout_minutes'), true,
        'inactivity fields must lock with their own master');

      await setToggle(page, 'login_lockout_enabled', true);
      await setToggle(page, 'inactivity_timeout_enabled', true);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('strong-password and inactivity tuning share one row but remain independent', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-auth-conditional-fields]');
      const layout = await page.evaluate(() => {
        const row = document.querySelector('[data-auth-conditional-fields]');
        const strong = row?.querySelector('[data-auth-strong-fields]');
        const inactivity = row?.querySelector('[data-auth-inactivity-fields]');
        if (!row || !strong || !inactivity) return { missing: true };
        const strongBox = strong.getBoundingClientRect();
        const inactivityBox = inactivity.getBoundingClientRect();
        return {
          sameParent: strong.parentElement === row && inactivity.parentElement === row,
          sameTop: Math.abs(strongBox.top - inactivityBox.top) <= 2,
          separated: strongBox.right <= inactivityBox.left || inactivityBox.right <= strongBox.left,
        };
      });

      assert.equal(layout.missing, undefined, 'the shared conditional row is incomplete');
      assert.equal(layout.sameParent, true, 'the controls are still in separate rows');
      assert.equal(layout.sameTop, true, 'the controls are not aligned on one row');
      assert.equal(layout.separated, true, 'the conditional fields overlap');
      assert.equal(await disabled(page, 'strong_password_min_length'), true);
      assert.equal(await disabled(page, 'inactivity_timeout_minutes'), true);

      await setToggle(page, 'enforce_strong_passwords', true);
      assert.equal(await disabled(page, 'strong_password_min_length'), false);
      assert.equal(await disabled(page, 'inactivity_timeout_minutes'), true);

      await setToggle(page, 'inactivity_timeout_enabled', true);
      assert.equal(await disabled(page, 'strong_password_min_length'), false);
      assert.equal(await disabled(page, 'inactivity_timeout_minutes'), false);

      await setToggle(page, 'enforce_strong_passwords', false);
      assert.equal(await disabled(page, 'strong_password_min_length'), true);
      assert.equal(await disabled(page, 'inactivity_timeout_minutes'), false);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('public page sidebar toggle is scoped without locking notification badges', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-dlux-settings-toggle-field="show_sidebar_on_public"]');
      const layout = await page.evaluate(() => {
        const notificationCard = document.querySelector(
          '[data-dlux-settings-toggle-field="sidebar_show_notification_badges"]',
        );
        const publicCard = document.querySelector(
          '[data-dlux-settings-toggle-field="show_sidebar_on_public"]',
        );
        const publicColumn = publicCard?.closest('.col-lg-6');
        const publicBlock = publicCard?.closest('[data-public-page-dependent]');
        if (!notificationCard || !publicColumn || !publicBlock) return { missing: true };
        return {
          scoped: publicBlock.contains(publicCard),
          unrelatedOutside: !publicBlock.contains(notificationCard),
        };
      });

      assert.equal(layout.missing, undefined, 'the public page sidebar toggle is missing');
      assert.equal(layout.scoped, true, 'the public page sidebar toggle is not scoped to public page access');
      assert.equal(layout.unrelatedOutside, true, 'notification badges must not be scoped to public page access');
      assert.equal(await disabled(page, 'show_sidebar_on_public'), true);
      assert.equal(await disabled(page, 'sidebar_show_notification_badges'), false);

      await setToggle(page, 'public_root', true);
      assert.equal(await disabled(page, 'show_sidebar_on_public'), false);
      assert.equal(await disabled(page, 'sidebar_show_notification_badges'), false);

      await setToggle(page, 'public_root', false);
      assert.equal(await disabled(page, 'show_sidebar_on_public'), true);
      assert.equal(await disabled(page, 'sidebar_show_notification_badges'), false);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('public page titlebar toggle is scoped without locking the language switcher', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-dlux-settings-toggle-field="show_titlebar_on_public"]');
      const layout = await page.evaluate(() => {
        const languageCard = document.querySelector(
          '[data-dlux-settings-toggle-field="titlebar_show_language_switcher"]',
        );
        const publicCard = document.querySelector(
          '[data-dlux-settings-toggle-field="show_titlebar_on_public"]',
        );
        const publicColumn = publicCard?.closest('.col-lg-6');
        const publicBlock = publicCard?.closest('[data-public-page-dependent]');
        if (!languageCard || !publicColumn || !publicBlock) return { missing: true };
        return {
          scoped: publicBlock.contains(publicCard),
          unrelatedOutside: !publicBlock.contains(languageCard),
        };
      });

      assert.equal(layout.missing, undefined, 'the public page titlebar toggle is missing');
      assert.equal(layout.scoped, true, 'the public page titlebar toggle is not scoped to public page access');
      assert.equal(layout.unrelatedOutside, true, 'language switcher must not be scoped to public page access');
      const languageDisabled = await disabled(page, 'titlebar_show_language_switcher');
      assert.equal(await disabled(page, 'show_titlebar_on_public'), true);

      await setToggle(page, 'public_root', true);
      assert.equal(await disabled(page, 'show_titlebar_on_public'), false);
      assert.equal(await disabled(page, 'titlebar_show_language_switcher'), languageDisabled);

      await setToggle(page, 'public_root', false);
      assert.equal(await disabled(page, 'show_titlebar_on_public'), true);
      assert.equal(await disabled(page, 'titlebar_show_language_switcher'), languageDisabled);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('client IP custom header is editable only in custom mode', async () => {
    // The header name is only meaningful when the mode says to read it. Leaving
    // it editable in x_forwarded_for mode invites a value that is silently
    // ignored — the exact UI/backend mismatch DSRP-1 forbids.
    const { ctx, page, errors } = await wizard();
    try {
      const mode = '.dlux-system-setup-form [name="client_ip_mode"]';
      assert.ok(await page.$(mode), 'client_ip_mode control missing');
      await stepContaining(page, '[data-client-ip-mode-input]');

      await page.selectOption(mode, 'custom');
      await page.waitForTimeout(200);
      assert.equal(await disabled(page, 'client_ip_custom_header'), false,
        'custom mode must allow editing the header name');

      await page.selectOption(mode, 'x_forwarded_for');
      await page.waitForTimeout(200);
      assert.equal(await disabled(page, 'client_ip_custom_header'), true,
        'the header name must lock outside custom mode');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('login layout choice drives which hero fields are shown', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      // login_style is a radio group rendered through the Dlux choice widget,
      // not a <select>; the real inputs sit behind styled labels.
      assert.ok(await page.$('.dlux-system-setup-form [name="login_style"]'),
        'login_style control missing');
      const pickStyle = (value) => page.evaluate((v) => {
        const el = document.querySelector(`.dlux-system-setup-form [name="login_style"][value="${v}"]`);
        if (!el) throw new Error(`login_style=${v} not found`);
        el.checked = true;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }, value);

      // Count by the class the code actually toggles, not by offsetParent —
      // the latter is null for every node while its step panel is hidden, which
      // would make both layouts read as zero and the comparison vacuous.
      const heroShown = () => page.evaluate(
        () => [...document.querySelectorAll('[data-login-hero-field]')]
          .filter((e) => !e.classList.contains('d-none')).length,
      );

      await pickStyle('split');
      await page.waitForTimeout(250);
      const withSplit = await heroShown();

      await pickStyle('fullpage');
      await page.waitForTimeout(250);
      const withFullpage = await heroShown();

      assert.equal(withSplit, 0, 'the split layout has no hero, so its fields must be hidden');
      assert.ok(withFullpage > 0, 'the fullpage layout must reveal its hero fields');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('locked titlebar language switcher explains and dims the whole card', async () => {
    await server.stop();
    server = await startServer({ configured: false, languageOverride: false });
    let ctx;
    try {
      const opened = await wizard();
      ({ ctx } = opened);
      const { page, errors } = opened;
      const selector = '[data-dlux-settings-toggle-field="titlebar_show_language_switcher"]';
      await stepContaining(page, selector);

      const state = await page.$eval(selector, (card) => ({
        inputDisabled: card.querySelector('input')?.disabled,
        dependent: card.classList.contains('dlux-dependent-settings'),
        dimmed: card.classList.contains('is-disabled'),
        ariaDisabled: card.getAttribute('aria-disabled'),
        tooltip: card.getAttribute('data-dlux-tooltip'),
        opacity: Number.parseFloat(getComputedStyle(card).opacity),
      }));

      assert.equal(state.inputDisabled, true);
      assert.equal(state.dependent, true);
      assert.equal(state.dimmed, true);
      assert.equal(state.ariaDisabled, 'true');
      assert.match(state.tooltip, /Allow users to change their display language/);
      assert.ok(state.opacity < 1, `locked card opacity should be dimmed, got ${state.opacity}`);

      await page.hover(selector);
      await page.waitForSelector('.dlux-tooltip.show');
      assert.match(await page.textContent('.dlux-tooltip.show'), /Allow users to change their display language/);
      assert.deepEqual(errors, []);
    } finally {
      if (ctx) await ctx.close();
      await server.stop();
      server = await startServer({ configured: false });
    }
  }, { timeout: 120000 });
});

// Functional tests for the wizard's email cluster:
// initEmailDeliveryOptions, initEmailApply, initEmailSendTest.
//
// Written BEFORE those three move to setup/js/email.js.
//
// The two action buttons POST to `email_config_apply` and `email_send_test`,
// which mutate stored configuration and attempt a real send. Every test here
// intercepts those routes with `page.route` and answers them itself, so the
// tests exercise the client behaviour — spinner, result message, payload —
// without touching the endpoints.
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
  await page.waitForTimeout(200);
}

async function setField(page, name, value) {
  await page.evaluate(([n, v]) => {
    const el = document.querySelector(`.dlux-system-setup-form [name="${n}"]`);
    if (!el) throw new Error(`field ${n} not found`);
    el.value = v;
    el.dispatchEvent(new Event('change', { bubbles: true }));
  }, [name, value]);
  await page.waitForTimeout(200);
}

/** Reveal the step owning `selector`. Inactive panels are display:none, so a
 *  click cannot land on them — not even with `force`, which still scrolls the
 *  element into view. Field reads and `setToggle` are unaffected. */
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
const value = (page, name) => page.inputValue(`.dlux-system-setup-form [name="${name}"]`);

describe('wizard email cluster', { concurrency: 1 }, () => {
  test('the email master gates the whole delivery block', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const gated = [
        'email_config_transport', 'email_config_host', 'email_config_port',
        'email_config_username', 'email_config_default_from_email',
        'email_config_test_recipient',
      ];

      await setToggle(page, 'email_config_enabled', true);
      for (const f of gated) {
        assert.equal(await disabled(page, f), false, `${f} should be editable while email is on`);
      }

      await setToggle(page, 'email_config_enabled', false);
      for (const f of gated) {
        assert.equal(await disabled(page, f), true, `${f} must lock while email is off`);
      }
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the password field is gated by secret storage, not just by the master', async () => {
    // A second, independent condition: the password is only editable when the
    // secret is stored encrypted in the database. Under any other storage mode
    // the field must stay locked even with email fully enabled, or an operator
    // types a secret that is never persisted where they think it is.
    const { ctx, page, errors } = await wizard();
    try {
      await setToggle(page, 'email_config_enabled', true);
      const storage = '.dlux-system-setup-form [name="email_config_secret_storage"]';
      assert.ok(await page.$(storage), 'secret storage control missing');

      await setField(page, 'email_config_secret_storage', 'encrypted_db');
      assert.equal(await disabled(page, 'email_config_password'), false,
        'encrypted_db storage must allow entering the password');

      const other = await page.evaluate((sel) => {
        const el = document.querySelector(sel);
        const opt = [...el.options].map((o) => o.value).find((v) => v !== 'encrypted_db');
        return opt || null;
      }, storage);
      if (other) {
        await setField(page, 'email_config_secret_storage', other);
        assert.equal(await disabled(page, 'email_config_password'), true,
          `password must lock under secret storage "${other}"`);
      }

      // And the master still wins over both.
      await setField(page, 'email_config_secret_storage', 'encrypted_db');
      await setToggle(page, 'email_config_enabled', false);
      assert.equal(await disabled(page, 'email_config_password'), true,
        'password must lock when the email master is off, whatever the storage mode');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a provider preset fills host, port and TLS', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await setToggle(page, 'email_config_enabled', true);
      const preset = '.dlux-system-setup-form [name="email_config_provider_preset"]';
      assert.ok(await page.$(preset), 'provider preset control missing');

      await setField(page, 'email_config_provider_preset', 'gmail');
      assert.equal(await value(page, 'email_config_host'), 'smtp.gmail.com');
      assert.equal(await value(page, 'email_config_port'), '587');
      assert.equal(await page.isChecked('.dlux-system-setup-form [name="email_config_use_tls"]'), true);
      assert.equal(await page.isChecked('.dlux-system-setup-form [name="email_config_use_ssl"]'), false);

      // The relay preset deliberately clears the host and uses the local port.
      await setField(page, 'email_config_provider_preset', 'relay');
      assert.equal(await value(page, 'email_config_port'), '1025');
      assert.equal(await page.isChecked('.dlux-system-setup-form [name="email_config_use_tls"]'), false);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('send test refuses to fire without a recipient', async () => {
    // The guard runs before the request, so a blank recipient must produce a
    // message and no network call at all.
    const { ctx, page, errors } = await wizard();
    try {
      let calls = 0;
      await page.route(/email\/send-test/, async (route) => {
        calls += 1;
        await route.fulfill({ status: 200, contentType: 'application/json', body: '{"ok": true}' });
      });

      await setToggle(page, 'email_config_enabled', true);
      await setField(page, 'email_config_test_recipient', '');
      await stepContaining(page, '[data-email-send-test]');
      await page.click('[data-email-send-test]');
      await page.waitForTimeout(400);

      assert.equal(calls, 0, 'a blank recipient must not reach the endpoint');
      const shown = await page.textContent('[data-email-send-test-result]');
      assert.ok((shown || '').trim().length > 0, 'the operator should be told why nothing happened');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('send test posts the recipient and reports the outcome', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      let posted = null;
      await page.route(/email\/send-test/, async (route) => {
        posted = route.request().postData();
        await route.fulfill({
          status: 200, contentType: 'application/json',
          body: JSON.stringify({ ok: true, message: 'sent-ok-marker' }),
        });
      });

      await setToggle(page, 'email_config_enabled', true);
      await setField(page, 'email_config_test_recipient', 'ops@example.com');
      await stepContaining(page, '[data-email-send-test]');
      await page.click('[data-email-send-test]');
      await page.waitForTimeout(600);

      assert.ok(posted && posted.includes('ops%40example.com') || (posted || '').includes('ops@example.com'),
        `the typed recipient was not sent; body was ${JSON.stringify(posted)}`);
      const shown = (await page.textContent('[data-email-send-test-result]') || '').trim();
      assert.ok(shown.length > 0, 'no result was reported to the operator');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a failed apply is reported, not swallowed', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await page.route(/email\/apply/, async (route) => {
        await route.fulfill({
          status: 502, contentType: 'application/json',
          body: JSON.stringify({ ok: false, message: 'apply-failed-marker' }),
        });
      });

      await setToggle(page, 'email_config_enabled', true);
      await stepContaining(page, '[data-email-apply]');
      await page.click('[data-email-apply]');
      await page.waitForTimeout(600);

      const shown = (await page.textContent('[data-email-apply-result]') || '').trim();
      assert.ok(shown.length > 0, 'a 502 from apply must surface to the operator');

      // The stub deliberately returns 502, and Chromium logs every failed
      // resource load as a console error. Ignore that one line; anything else,
      // especially a thrown exception, still fails the test.
      const unexpected = errors.filter((e) => !/Failed to load resource/.test(e));
      assert.deepEqual(unexpected, []);
    } finally { await ctx.close(); }
  });
});

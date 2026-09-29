// The setup wizard's Project settings step: a project's register_app_settings()
// tiles, as one extra step after Dlux's own.
//
// The Python tests prove the server renders and saves it. Only a browser shows
// the wizard's JS treating a nineteenth panel like the others: the nav opening
// it, Save appearing on it, and a rejected value bringing the operator back to
// it rather than to step one.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, openWizard, chromium, BASE } from './server.mjs';

const LIMIT = 'app__e2e_project-limit';

let server;
let browser;

before(async () => {
  server = await startServer({ configured: false, projectSettings: true });
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

async function openLastStep(page) {
  const last = await page.evaluate(() => document.querySelectorAll('.wizard-step').length - 1);
  await page.click(`[data-dlux-wizard-step-target="${last}"]`);
  await page.waitForFunction(
    (n) => [...document.querySelectorAll('.wizard-step')].findIndex((s) => !s.classList.contains('d-none')) === n,
    last, { timeout: 5000 },
  );
  return last;
}

describe('setup wizard project settings step', { concurrency: 1 }, () => {
  test('every nav button still opens the panel it names', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const counts = await page.evaluate(() => ({
        navs: document.querySelectorAll('[data-dlux-wizard-step-target]').length,
        panels: document.querySelectorAll('.wizard-step').length,
      }));
      assert.equal(counts.navs, counts.panels, 'one nav button per panel');
      for (let index = 0; index < counts.panels; index += 1) {
        await page.click(`[data-dlux-wizard-step-target="${index}"]`);
        await page.waitForTimeout(80);
        assert.equal(await visibleStep(page), index, `nav ${index} opened another panel`);
      }
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the project step is last, carries the tile, and offers Save', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await openLastStep(page);
      const step = page.locator('.wizard-step:not(.d-none)');
      assert.equal(await step.getAttribute('data-dlux-project-settings-step'), '');
      assert.match(await step.locator('.dlux-setup-step-badge').innerText(), /Step 19: Project Settings/);
      assert.match(await step.innerText(), /E2E Project/);
      assert.equal(await page.inputValue(`input[name="${LIMIT}"]`), '5', 'the tile default is the initial value');
      assert.equal(await page.isVisible('.dlux-btn-submit'), true);
      assert.equal(await page.isVisible('.dlux-btn-next'), false);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a value the server rejects brings the wizard back on the project step', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const last = await openLastStep(page);
      // Past the browser's own max check, so the server is the one refusing.
      await page.evaluate((name) => document.querySelector(`input[name="${name}"]`).removeAttribute('max'), LIMIT);
      await page.fill(`input[name="${LIMIT}"]`, '99');
      await Promise.all([
        page.waitForLoadState('networkidle'),
        page.evaluate(() => document.querySelector('.dlux-btn-submit').click()),
      ]);
      await page.waitForSelector('.dlux-system-setup-form', { timeout: 10000 });
      assert.match(page.url(), /\/sys\/setup\/$/, 'the wizard stays open');
      assert.equal(await visibleStep(page), last, 'reopened on the step with the error');
      assert.equal(await page.isVisible('.wizard-step:not(.d-none) .invalid-feedback'), true);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a valid submit finishes setup', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await openLastStep(page);
      await page.fill(`input[name="${LIMIT}"]`, '12');
      await Promise.all([
        page.waitForURL((url) => !url.pathname.startsWith('/sys/setup/'), { timeout: 15000 }),
        page.evaluate(() => document.querySelector('.dlux-btn-submit').click()),
      ]);
      await page.goto(`${BASE}/sys/setup/`, { waitUntil: 'networkidle' });
      assert.doesNotMatch(page.url(), /\/sys\/setup\/$/, 'a configured system leaves the wizard');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

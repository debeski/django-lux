// The setup wizard's step nav must open the step it names.
//
// Found while adding the Extra Features step. The wizard rendered 14 panels but
// the nav only had 13 buttons — the Email panel had none — and `showStep()`
// indexes straight into the panel list. So every button from "Access & Security"
// onward opened the panel before the one it named:
//
//     Access & Security -> Step 3: Email
//     Backups           -> Step 13: Profile Page
//
// and Step 14 (Backups) could not be reached from the nav at all.
//
// Nothing caught it: the Python tests assert that targets 0, 6 and 12 exist, and
// counting buttons would have passed too. Only following a click through to the
// panel it reveals catches an off-by-one, so that is what this does.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';

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

async function wizardPage() {
  const { ctx, page, errors } = await loggedInPage(browser);
  await page.goto(`${BASE}/sys/setup/`, { waitUntil: 'networkidle' });
  // The wizard only renders once a setup language is chosen.
  const start = await page.$('[data-setup-language-start="en"]');
  if (start) {
    await start.click();
    await page.waitForLoadState('networkidle');
  }
  return { ctx, page, errors };
}

describe('setup wizard step nav', { concurrency: 1 }, () => {
  test('every nav button opens the panel it names', async () => {
    const { ctx, page } = await wizardPage();
    try {
      const rows = await page.evaluate(async () => {
        const navs = [...document.querySelectorAll('[data-dlux-wizard-step-target]')];
        const out = [];
        for (const nav of navs) {
          nav.click();
          await new Promise((resolve) => setTimeout(resolve, 90));
          const visible = [...document.querySelectorAll('.wizard-step')]
            .find((step) => !step.classList.contains('d-none'));
          out.push({
            target: Number(nav.dataset.dluxWizardStepTarget),
            index: visible ? [...document.querySelectorAll('.wizard-step')].indexOf(visible) : -1,
          });
        }
        return out;
      });

      assert.ok(rows.length > 0, 'the step nav did not render');
      for (const row of rows) {
        assert.equal(
          row.index, row.target,
          `nav button ${row.target} opened panel ${row.index}`,
        );
      }
    } finally { await ctx.close(); }
  });

  test('there is exactly one nav button per panel', async () => {
    // The root cause: a panel with no button silently shifts every later one.
    const { ctx, page } = await wizardPage();
    try {
      const counts = await page.evaluate(() => ({
        panels: document.querySelectorAll('.wizard-step').length,
        navs: document.querySelectorAll('[data-dlux-wizard-step-target]').length,
      }));
      assert.equal(
        counts.navs, counts.panels,
        `${counts.panels} panels but ${counts.navs} nav buttons — the extra panels are unreachable`,
      );
    } finally { await ctx.close(); }
  });

  test('the last step is reachable from the nav', async () => {
    // Backups was the last step and had no button that reached it.
    const { ctx, page } = await wizardPage();
    try {
      const reached = await page.evaluate(async () => {
        const navs = [...document.querySelectorAll('[data-dlux-wizard-step-target]')];
        const last = navs[navs.length - 1];
        last.click();
        await new Promise((resolve) => setTimeout(resolve, 120));
        const panels = [...document.querySelectorAll('.wizard-step')];
        const visible = panels.find((step) => !step.classList.contains('d-none'));
        return panels.indexOf(visible) === panels.length - 1;
      });
      assert.equal(reached, true, 'the final panel cannot be opened from the nav');
    } finally { await ctx.close(); }
  });

  test('the Extra Features step carries the ScanLink toggle', async () => {
    const { ctx, page } = await wizardPage();
    try {
      const found = await page.evaluate(async () => {
        const navs = [...document.querySelectorAll('[data-dlux-wizard-step-target]')];
        navs[navs.length - 1].click();
        await new Promise((resolve) => setTimeout(resolve, 120));
        const panels = [...document.querySelectorAll('.wizard-step')];
        const visible = panels.find((step) => !step.classList.contains('d-none'));
        return !!visible && !!visible.querySelector('[name="scanlink_enabled"]');
      });
      assert.equal(found, true, 'the ScanLink toggle is not on the Extra Features step');
    } finally { await ctx.close(); }
  });
});

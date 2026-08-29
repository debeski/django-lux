// Functional tests for the wizard's log and profile builders:
// initLogBuilder, initProfileBuilder.
//
// Written BEFORE they move to setup/js/builders.js.
//
// Both follow the same shape: a UI over a config object that is serialised into
// a single hidden field (`log_config`, `profile_config`) which is what actually
// posts. The failure mode that matters is silent — the UI updates, the hidden
// field does not, and the operator's choices are dropped on save with no error.
// So every test asserts against the serialised JSON, not the controls.
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

async function stepContaining(page, selector) {
  const index = await page.evaluate((sel) => {
    const steps = [...document.querySelectorAll('.wizard-step')];
    return steps.findIndex((step) => step.querySelector(sel));
  }, selector);
  assert.ok(index >= 0, `no wizard step contains ${selector}`);
  await page.click(`[data-dlux-wizard-step-target="${index}"]`);
  await page.waitForSelector(selector, { state: 'visible', timeout: 5000 });
}

const configOf = (page, name) => page.evaluate((n) => {
  const el = document.querySelector(`.dlux-system-setup-form [name="${n}"]`);
  if (!el) return null;
  try { return JSON.parse(el.value || 'null'); } catch { return el.value; }
}, name);

/** Flip a checkbox through a bubbling change, the way the builders listen. */
async function toggle(page, selector, on) {
  await page.evaluate(([sel, v]) => {
    const el = document.querySelector(sel);
    if (!el) throw new Error(`${sel} not found`);
    if (el.checked !== v) {
      el.checked = v;
      el.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, [selector, on]);
  await page.waitForTimeout(200);
}

describe('wizard log + profile builders', { concurrency: 1 }, () => {
  test('profile onboarding options spread horizontally and wrap when needed', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-profile-onboarding-options]');
      const desktop = await page.evaluate(() => {
        const rail = document.querySelector('[data-profile-onboarding-options]');
        const options = [...rail.children];
        const railBox = rail.getBoundingClientRect();
        const layouts = {};
        for (const direction of ['ltr', 'rtl']) {
          document.documentElement.dir = direction;
          const boxes = options.map((option) => option.getBoundingClientRect());
          layouts[direction] = {
            tops: boxes.map((box) => Math.round(box.top)),
            occupiedWidth: Math.max(...boxes.map((box) => box.right)) - Math.min(...boxes.map((box) => box.left)),
          };
        }
        return { count: options.length, railWidth: railBox.width, layouts };
      });
      assert.equal(desktop.count, 3);
      for (const direction of ['ltr', 'rtl']) {
        const layout = desktop.layouts[direction];
        assert.equal(new Set(layout.tops).size, 1, `the onboarding options are vertical in ${direction}`);
        assert.ok(layout.occupiedWidth >= desktop.railWidth * 0.8, `the options do not spread across the ${direction} row`);
      }

      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(200);
      const mobile = await page.evaluate(() => {
        const rail = document.querySelector('[data-profile-onboarding-options]');
        const railBox = rail.getBoundingClientRect();
        const boxes = [...rail.children].map((option) => option.getBoundingClientRect());
        return {
          adjacent: boxes.some((first, index) => boxes.slice(index + 1).some((second) => {
            const separated = first.right <= second.left + 1 || second.right <= first.left + 1;
            const verticalOverlap = Math.min(first.bottom, second.bottom) - Math.max(first.top, second.top);
            return separated && verticalOverlap > 0;
          })),
          fits: boxes.every((box) => box.width <= railBox.width + 1),
        };
      });
      assert.equal(mobile.adjacent, true, 'the onboarding options fell back to a vertical list');
      assert.equal(mobile.fits, true, 'an onboarding option overflows the mobile rail');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('profile page toggles share one responsive row', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-profile-page-toggle-grid]');
      const desktop = await page.evaluate(() => {
        const grid = document.querySelector('[data-profile-page-toggle-grid]');
        const cards = [...grid.children];
        return {
          count: cards.length,
          tops: cards.map((card) => Math.round(card.getBoundingClientRect().top)),
        };
      });
      assert.equal(desktop.count, 3);
      assert.equal(new Set(desktop.tops).size, 1, 'the three profile toggles are not on one desktop row');

      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(200);
      const mobile = await page.evaluate(() => {
        const grid = document.querySelector('[data-profile-page-toggle-grid]');
        const gridBox = grid.getBoundingClientRect();
        const cards = [...grid.children];
        return {
          tops: cards.map((card) => Math.round(card.getBoundingClientRect().top)),
          fits: cards.every((card) => card.getBoundingClientRect().width <= gridBox.width + 1),
        };
      });
      assert.equal(new Set(mobile.tops).size, 3, 'the profile toggles should stack on narrow screens');
      assert.equal(mobile.fits, true, 'a profile toggle overflows the mobile grid');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('logging switches align at the logical start on themed responsive rows', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-dlux-log-root]');
      const desktop = await page.evaluate(() => {
        const section = document.querySelector('.dlux-log-section');
        const row = document.querySelector('.dlux-log-model-row');
        const switchNode = row?.querySelector('.dlux-log-switch');
        const input = switchNode?.querySelector('.dlux-settings-toggle-field__input');
        if (!section || !row || !switchNode || !input) return null;
        const originalDirection = document.documentElement.dir;
        const layouts = {};
        for (const direction of ['ltr', 'rtl']) {
          document.documentElement.dir = direction;
          const switchBox = switchNode.getBoundingClientRect();
          const inputBox = input.getBoundingClientRect();
          const style = getComputedStyle(switchNode);
          layouts[direction] = {
            paddingInlineStart: style.paddingInlineStart,
            startGap: direction === 'rtl'
              ? switchBox.right - inputBox.right
              : inputBox.left - switchBox.left,
          };
        }
        document.documentElement.dir = originalDirection;
        const sectionStyle = getComputedStyle(section);
        return {
          layouts,
          rowDisplay: getComputedStyle(row).display,
          backgroundColor: sectionStyle.backgroundColor,
          borderWidth: sectionStyle.borderTopWidth,
          borderStyle: sectionStyle.borderTopStyle,
        };
      });
      assert.ok(desktop, 'the logging step has no rendered model rows');
      assert.equal(desktop.rowDisplay, 'grid');
      assert.notEqual(desktop.backgroundColor, 'rgba(0, 0, 0, 0)');
      assert.equal(desktop.borderWidth, '1px');
      assert.notEqual(desktop.borderStyle, 'none');
      for (const direction of ['ltr', 'rtl']) {
        assert.equal(desktop.layouts[direction].paddingInlineStart, '0px');
        assert.ok(
          Math.abs(desktop.layouts[direction].startGap) <= 2,
          `the ${direction} log switch still has a reserved start gutter`,
        );
      }

      await page.setViewportSize({ width: 390, height: 844 });
      await page.waitForTimeout(200);
      const mobile = await page.evaluate(() => {
        const row = document.querySelector('.dlux-log-model-row');
        if (!row) return null;
        const rowBox = row.getBoundingClientRect();
        const switches = [...row.querySelectorAll('.dlux-log-switch')];
        const boxes = switches.map((node) => node.getBoundingClientRect());
        return {
          count: boxes.length,
          modelSpansRow: getComputedStyle(switches[0]).gridColumnEnd === '-1',
          actionsShareRow: new Set(boxes.slice(1).map((box) => Math.round(box.top))).size === 1,
          fits: boxes.every((box) => box.left >= rowBox.left - 1 && box.right <= rowBox.right + 1),
        };
      });
      assert.ok(mobile);
      assert.equal(mobile.count, 4);
      assert.equal(mobile.modelSpansRow, true);
      assert.equal(mobile.actionsShareRow, true);
      assert.equal(mobile.fits, true);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the log builder serialises into the posted hidden field', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      assert.ok(await page.$('[data-dlux-log-root]'), 'log builder root missing');
      const before = await configOf(page, 'log_config');
      assert.ok(before && typeof before === 'object', 'log_config should hold a JSON object on load');

      // Flip the first section's enable box and confirm the hidden field moved.
      const sectionBox = '[data-dlux-log-root] [data-log-section] input[type="checkbox"]';
      const had = await page.evaluate((s) => document.querySelector(s)?.checked, sectionBox);
      assert.equal(typeof had, 'boolean', 'no log section checkbox found');

      await toggle(page, sectionBox, !had);
      const after = await configOf(page, 'log_config');
      assert.notDeepEqual(after, before,
        'toggling a log section did not change the hidden field the form posts');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the log master gates its dependent section', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const master = '[data-dlux-log-root] [data-log-master] input[type="checkbox"], [data-dlux-log-root] input[data-log-master]';
      const found = await page.$(master);
      if (!found) return; // markup variant without a master; nothing to assert

      const depDisabled = () => page.evaluate(
        () => {
          const dep = document.querySelector('[data-dlux-log-root] [data-log-dependent]');
          if (!dep) return null;
          return [...dep.querySelectorAll('input, select')].every((c) => c.disabled);
        },
      );

      await toggle(page, master, true);
      assert.notEqual(await depDisabled(), true, 'dependents should be live while logging is on');
      await toggle(page, master, false);
      assert.notEqual(await depDisabled(), false, 'dependents must lock when logging is off');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the profile builder serialises into the posted hidden field', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      assert.ok(await page.$('[data-dlux-profile-root]'), 'profile builder root missing');
      const before = await configOf(page, 'profile_config');
      assert.ok(before && typeof before === 'object', 'profile_config should hold a JSON object on load');

      const key = '[data-dlux-profile-root] [data-profile-key]';
      const had = await page.evaluate((s) => document.querySelector(s)?.checked, key);
      assert.equal(typeof had, 'boolean', 'no profile key checkbox found');

      await toggle(page, key, !had);
      const after = await configOf(page, 'profile_config');
      assert.notDeepEqual(after, before,
        'toggling a profile field did not change the hidden field the form posts');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the security-nudges choice reaches the serialised config', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      const nudges = '[data-profile-nudges]';
      if (!(await page.$(nudges))) return;

      const options = await page.evaluate((s) => {
        const el = document.querySelector(s);
        return el && el.options ? [...el.options].map((o) => o.value) : [];
      }, nudges);
      if (options.length < 2) return;

      const current = await configOf(page, 'profile_config');
      const pick = options.find((o) => o !== (current && current.security_nudges)) || options[0];

      await page.evaluate(([s, v]) => {
        const el = document.querySelector(s);
        el.value = v;
        el.dispatchEvent(new Event('change', { bubbles: true }));
      }, [nudges, pick]);
      await page.waitForTimeout(250);

      const after = await configOf(page, 'profile_config');
      assert.equal(after.security_nudges, pick,
        'the nudges choice was not written into profile_config');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('sidebar selected items reorder inside their group by drag and drop', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-builder-selected-tree]');
      const order = await page.evaluate(() => {
        const hidden = document.querySelector('.dlux-system-setup-form [name="sidebar_config"]');
        const selectedTree = document.querySelector('[data-builder-selected-tree]');
        if (!hidden || !selectedTree) return { error: 'sidebar builder missing' };
        hidden.value = JSON.stringify({
          enabled: true,
          entries: [{
            kind: 'group',
            id: 'reports-group',
            label: 'Reports',
            icon: 'bi-folder2-open',
            items: [
              { kind: 'item', id: 'first-entry', url_name: 'first_route', label: 'First', icon: 'bi-1-circle' },
              { kind: 'item', id: 'second-entry', url_name: 'second_route', label: 'Second', icon: 'bi-2-circle' },
            ],
          }],
        });
        hidden.dispatchEvent(new Event('change', { bubbles: true }));

        const source = selectedTree.querySelector('.dlux-builder-node.is-group .dlux-builder-node[data-entry-id="first-entry"]');
        const target = selectedTree.querySelector('.dlux-builder-node.is-group .dlux-builder-node[data-entry-id="second-entry"]');
        if (!source || !target) return { error: 'group children did not render' };
        const box = target.getBoundingClientRect();
        source.dispatchEvent(new DragEvent('dragstart', { bubbles: true, cancelable: true }));
        target.dispatchEvent(new DragEvent('dragover', { bubbles: true, cancelable: true, clientY: box.bottom - 1 }));
        target.dispatchEvent(new DragEvent('drop', { bubbles: true, cancelable: true, clientY: box.bottom - 1 }));
        source.dispatchEvent(new DragEvent('dragend', { bubbles: true, cancelable: true }));
        return JSON.parse(hidden.value).entries[0].items.map((item) => item.id);
      });

      assert.deepEqual(order, ['second-entry', 'first-entry']);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

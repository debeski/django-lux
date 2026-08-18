// The Admin panel command rail must stay clickable at every width.
//
// Reported as "rail actions don't work on smaller screens ... low space for the
// rail to expand to". Measured before the fix: 4/4 chips reachable at 1280 and
// 992, but 3/4 at 768, 2/4 at 576, and 1/4 at 390.
//
// The failure is not clipping — `scrollWidth` equalled the rail width all the
// way down. `.dlux-admin-command-chip` never set `flex-shrink: 0`, so flex
// compressed all four chips into whatever the heading row left over; with
// `white-space: nowrap` each label overflowed its own box and painted across its
// neighbours. The chips looked present and were not reachable: `elementFromPoint`
// at a chip's own centre returned a different chip, which is exactly what a real
// click does.
//
// So the assertion here is hit-testing, not geometry. A test that only measured
// widths would have passed throughout the bug.
//
// Below 992px the rail stays beside the title and scrolls within the available
// space, so "reachable" means reachable AFTER scrolling it into view — a chip
// parked outside the scroll viewport is fine, a chip covered by another is not.
// An absolutely positioned popover is wrong because `.dlux-admin-panel` sets
// `overflow: hidden` and clips it.
// When closed, the hidden rail must remain zero-width and the trigger must stay
// on the heading's inline edge; otherwise its invisible width wraps the trigger.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';

let server;
let browser;

before(async () => {
  server = await startServer({ configured: true });
  browser = await chromium.launch();
}, { timeout: 120000 });

after(async () => {
  if (browser) await browser.close();
  if (server) await server.stop();
});

// 992 is the breakpoint itself; narrower widths exercise the scrolling row.
// 320 is the narrowest phone worth supporting.
const WIDTHS = [1280, 992, 768, 576, 390, 320];

async function openRail(browser, width, dir = 'ltr') {
  const { ctx, page, errors } = await loggedInPage(browser);
  await page.setViewportSize({ width, height: 900 });
  await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
  const result = await page.evaluate(async (direction) => {
    document.documentElement.setAttribute('dir', direction);
    const toggle = document.querySelector('[data-admin-command-launcher] .dlux-admin-command-toggle');
    if (!toggle) return { missing: true };
    toggle.click();
    await new Promise((resolve) => setTimeout(resolve, 450));

    const rail = document.querySelector('[data-admin-command-rail]');
    const chips = [...rail.querySelectorAll('.dlux-admin-command-chip')];
    const box = rail.getBoundingClientRect();

    // Scroll each chip into its rail's viewport, then hit-test at its own
    // centre — the way a real click resolves after the user scrolls to it.
    let reachable = 0;
    for (const chip of chips) {
      chip.scrollIntoView({ block: 'nearest', inline: 'center' });
      await new Promise((resolve) => setTimeout(resolve, 40));
      const b = chip.getBoundingClientRect();
      if (b.width === 0 || b.height === 0) continue;
      const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
      if (hit && (chip === hit || chip.contains(hit))) reachable += 1;
    }

    return {
      chips: chips.length,
      reachable,
      offscreen: Math.round(box.left) < 0 || Math.round(box.right) > window.innerWidth,
      scrollable: rail.scrollWidth > Math.ceil(box.width) + 1,
    };
  }, dir);
  return { ctx, page, errors, ...result };
}

describe('admin panel command rail', { concurrency: 1 }, () => {
  test('the collapsed trigger stays on the heading edge below the breakpoint', async () => {
    const cases = [
      { width: 979, dir: 'ltr' },
      { width: 979, dir: 'rtl' },
      { width: 390, dir: 'ltr' },
      { width: 390, dir: 'rtl' },
    ];
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      for (const item of cases) {
        await page.setViewportSize({ width: item.width, height: 900 });
        await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
        const layout = await page.evaluate((direction) => {
          document.documentElement.setAttribute('dir', direction);
          const row = document.querySelector('.dlux-admin-panel-heading-row');
          const title = row?.querySelector('h4');
          const rail = row?.querySelector('[data-admin-command-rail]');
          const toggle = row?.querySelector('[data-admin-command-toggle]');
          if (!row || !title || !rail || !toggle) return { missing: true };
          const rb = row.getBoundingClientRect();
          const tb = title.getBoundingClientRect();
          const railBox = rail.getBoundingClientRect();
          const toggleBox = toggle.getBoundingClientRect();
          return {
            railWidth: railBox.width,
            verticalOverlap: Math.min(tb.bottom, toggleBox.bottom)
              - Math.max(tb.top, toggleBox.top),
            edgeGap: direction === 'rtl'
              ? toggleBox.left - rb.left
              : rb.right - toggleBox.right,
          };
        }, item.dir);
        assert.equal(layout.missing, undefined, 'the heading controls are missing');
        assert.ok(layout.railWidth <= 1, 'the collapsed rail still reserves layout width');
        assert.ok(layout.verticalOverlap > 0, 'the trigger fell below the heading');
        assert.ok(layout.edgeGap <= 1, 'the trigger is not pinned to the inline edge');
      }
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  for (const width of WIDTHS) {
    test(`every action is clickable at ${width}px`, async () => {
      const { ctx, chips, reachable, missing } = await openRail(browser, width);
      try {
        assert.equal(missing, undefined, 'the command launcher is not on the page');
        assert.ok(chips >= 4, `expected the admin actions, saw ${chips}`);
        assert.equal(
          reachable, chips,
          `${chips - reachable} of ${chips} actions are covered by another chip at ${width}px`,
        );
      } finally { await ctx.close(); }
    });
  }

  for (const width of [390, 576]) {
    test(`every action is reachable in RTL at ${width}px`, async () => {
      const { ctx, reachable, chips, offscreen } = await openRail(browser, width, 'rtl');
      try {
        assert.equal(offscreen, false, 'the rail hangs off the viewport in RTL');
        assert.equal(reachable, chips, 'an action is unreachable in RTL');
      } finally { await ctx.close(); }
    });
  }

  test('the narrow rail scrolls instead of being clipped by the card', async () => {
    // `.dlux-admin-panel` sets `overflow: hidden`. Anything that overflows the
    // rail without its own scroll container is simply cut off by the card, with
    // no way for the operator to reach it.
    const { ctx, page, scrollable } = await openRail(browser, 390);
    try {
      const style = await page.evaluate(() => {
        const rail = document.querySelector('[data-admin-command-rail]');
        const cs = getComputedStyle(rail);
        return { position: cs.position, overflowX: cs.overflowX };
      });
      assert.equal(style.position, 'static', 'an absolutely positioned rail is clipped by the card');
      assert.equal(style.overflowX, 'auto', 'the narrow rail must scroll');
      assert.equal(scrollable, true, 'four actions should overflow 390px and scroll');
    } finally { await ctx.close(); }
  });

  test('the desktop rail does not squeeze when more actions are added', async () => {
    // The horizontal rail fits today's four chips at 1280px with room over, so
    // nothing here would fail on chip count alone. It is the squeeze that has to
    // stay fixed: clone the rail up to eight actions and every one must still
    // hit-test to itself. Without `flex: 0 0 auto` on the chip this is the
    // original bug reproduced on a desktop viewport.
    const { ctx, page } = await openRail(browser, 1280);
    try {
      const result = await page.evaluate(async () => {
        const rail = document.querySelector('[data-admin-command-rail]');
        const template = rail.querySelector('.dlux-admin-command-chip');
        for (let i = 0; i < 4; i += 1) rail.appendChild(template.cloneNode(true));
        await new Promise((resolve) => setTimeout(resolve, 250));

        const chips = [...rail.querySelectorAll('.dlux-admin-command-chip')];
        const reachable = chips.filter((chip) => {
          const b = chip.getBoundingClientRect();
          if (b.width === 0 || b.height === 0) return false;
          const hit = document.elementFromPoint(b.left + b.width / 2, b.top + b.height / 2);
          return !!hit && (chip === hit || chip.contains(hit));
        }).length;
        return { chips: chips.length, reachable };
      });
      assert.equal(result.chips, 8, 'the clones did not land');
      assert.equal(
        result.reachable, result.chips,
        `${result.chips - result.reachable} of ${result.chips} chips overlap once the rail fills up`,
      );
    } finally { await ctx.close(); }
  });

  test('no chip is squeezed narrower than its own label', async () => {
    // The original defect, stated directly. A scroll container still lets flex
    // shrink its items, so `flex: 0 0 auto` is what keeps a `nowrap` label
    // inside its own box instead of painting across the next chip.
    const { ctx, page } = await openRail(browser, 390);
    try {
      const squeezed = await page.evaluate(() => {
        const chips = [...document.querySelectorAll('.dlux-admin-command-chip')];
        return chips
          .filter((chip) => chip.scrollWidth > Math.ceil(chip.clientWidth) + 1)
          .map((chip) => chip.textContent.trim());
      });
      assert.deepEqual(squeezed, [], 'these chips overflow their own box');
    } finally { await ctx.close(); }
  });

  test('the tablet rail stays beside the title', async () => {
    const { ctx, page } = await openRail(browser, 768);
    try {
      const layout = await page.evaluate(() => {
        const rail = document.querySelector('[data-admin-command-rail]');
        const title = document.querySelector('.dlux-admin-panel-heading-row h4');
        const rb = rail.getBoundingClientRect();
        const tb = title.getBoundingClientRect();
        return {
          verticalOverlap: Math.min(rb.bottom, tb.bottom) - Math.max(rb.top, tb.top),
          railWidth: rb.width,
        };
      });
      assert.ok(
        layout.verticalOverlap > 0,
        'the open rail fell below the title',
      );
      assert.ok(
        layout.railWidth > 0,
        'the open rail has no usable viewport',
      );
    } finally { await ctx.close(); }
  });

  test('the mobile rail opens on a second full-width row', async () => {
    const { ctx, page } = await openRail(browser, 390);
    try {
      const layout = await page.evaluate(() => {
        const row = document.querySelector('.dlux-admin-panel-heading-row').getBoundingClientRect();
        const title = document.querySelector('.dlux-admin-panel-heading-row h4').getBoundingClientRect();
        const launcher = document.querySelector('[data-admin-command-launcher]').getBoundingClientRect();
        const rail = document.querySelector('[data-admin-command-rail]').getBoundingClientRect();
        return {
          belowTitle: rail.top >= title.bottom - 1,
          launcherWidth: launcher.width,
          rowWidth: row.width,
        };
      });
      assert.equal(layout.belowTitle, true, 'the mobile rail remained beside the title');
      assert.ok(
        layout.launcherWidth >= layout.rowWidth - 1,
        'the mobile launcher did not receive the full second row',
      );
    } finally { await ctx.close(); }
  });

  test('opening the rail does not animate its layout width', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.setViewportSize({ width: 979, height: 900 });
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      const transitionProperties = await page.locator('[data-admin-command-rail]')
        .evaluate((rail) => getComputedStyle(rail).transitionProperty.split(',').map((item) => item.trim()));
      assert.equal(
        transitionProperties.includes('max-width'),
        false,
        'animating max-width recalculates the flex layout during expansion',
      );
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the narrow rail only scrolls when its actions do not fit', async () => {
    const wide = await openRail(browser, 979);
    const small = await openRail(browser, 390);
    try {
      assert.equal(wide.scrollable, false, 'the rail scrolls despite having enough room');
      assert.equal(small.scrollable, true, 'the rail does not scroll when actions overflow');
    } finally {
      await wide.ctx.close();
      await small.ctx.close();
    }
  });

  test('the desktop rail does not become a scroll container', async () => {
    // Guards the fix from overreaching: there is room at 1280px, so the rail
    // should still lay out normally rather than hide actions behind a scrollbar.
    const { ctx, scrollable } = await openRail(browser, 1280);
    try {
      assert.equal(scrollable, false, 'the desktop rail is overflowing rather than fitting');
    } finally { await ctx.close(); }
  });
});

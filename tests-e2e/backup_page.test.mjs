// Backup and restore page layout.
//
// `.dlux-backup-page` is a CSS grid, so ANY element added as a direct child
// becomes a new row — plus the 1.35rem grid gap. Adding a Back link as a
// top-level wrapper did exactly that: it pushed the whole page down, overflowed
// the viewport and shoved the footer up over the content while scrolling.
//
// The lesson is structural, so the test is structural: the link belongs inside
// an existing cell. Since 1.8.3 it is the page's Ribbon action (a
// `.dlux-back-link` to Options), not a `.dlux-backup-back` element of its own. The grid also needs a layout boundary: without one, its
// overflow can make the document scroller taller while `body.scrollHeight`
// remains viewport-sized. A final wheel gesture then scrolls the whole shell.
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

const BACK_LINK = '.dlux-backup-page .dlux-back-link[href$="/options/"]';

async function backupPage(dir = 'ltr') {
  const { ctx, page } = await loggedInPage(browser);
  await page.setViewportSize({ width: 1400, height: 900 });
  await page.goto(`${BASE}/sys/backup/`, { waitUntil: 'networkidle' });
  await page.evaluate((d) => document.documentElement.setAttribute('dir', d), dir);
  return { ctx, page };
}

describe('backup page layout', { concurrency: 1 }, () => {
  test('the Back link lives inside an existing grid cell', async () => {
    // The regression, stated exactly. Checking the link's own parent is not
    // enough — wrapping it in a div moves it one level down while still adding
    // a grid row. What matters is that it sits inside the Ribbon cell.
    const { ctx, page } = await backupPage();
    try {
      const placement = await page.evaluate((selector) => {
        const link = document.querySelector(selector);
        const grid = document.querySelector('.dlux-backup-page');
        if (!link || !grid) return { missing: true };
        // Which direct child of the grid contains it?
        const cell = [...grid.children].find((child) => child.contains(link));
        return {
          insideRibbon: !!link.closest('.dlux-ribbon-header'),
          cellIsRibbon: !!cell && cell.classList.contains('dlux-ribbon-header'),
          gridRows: grid.children.length,
        };
      }, BACK_LINK);
      assert.equal(placement.missing, undefined, 'the Back link is not on the page');
      assert.equal(placement.insideRibbon, true, 'the Back link is outside the Ribbon');
      assert.equal(
        placement.cellIsRibbon, true,
        'the Back link introduced its own grid row instead of using the Ribbon cell',
      );
    } finally { await ctx.close(); }
  });

  test('the inner page scroll never escapes to the document shell', async () => {
    const { ctx, page } = await backupPage();
    try {
      const size = await page.evaluate(() => {
        const main = document.querySelector('#mainContent');
        const root = document.scrollingElement;
        main.scrollTop = main.scrollHeight;
        return {
          documentOverflow: root.scrollHeight - root.clientHeight,
          mainAtEnd: main.scrollTop === main.scrollHeight - main.clientHeight,
        };
      });
      assert.ok(
        size.documentOverflow <= 1,
        `the document gained ${size.documentOverflow}px of scroll range outside #mainContent`,
      );
      assert.equal(size.mainAtEnd, true, 'the backup page did not scroll to its inner end');

      await page.mouse.move(1000, 700);
      await page.mouse.wheel(0, 1600);
      await page.waitForTimeout(50);
      const afterWheel = await page.evaluate(() => {
        const sidebar = document.querySelector('.sidebar');
        return {
          documentTop: document.scrollingElement.scrollTop,
          sidebarTop: sidebar?.getBoundingClientRect().top,
          titlebarBottom: document.querySelector('.titlebar').getBoundingClientRect().bottom,
        };
      });
      assert.equal(afterWheel.documentTop, 0, 'a final wheel gesture scrolled the document shell');
      assert.ok(
        Math.abs(afterWheel.sidebarTop - afterWheel.titlebarBottom) <= 1,
        'the sidebar moved away from the titlebar after the inner pane ended',
      );
    } finally { await ctx.close(); }
  });

  for (const dir of ['ltr', 'rtl']) {
    test(`the Back link sits at the inline end in ${dir}`, async () => {
      const { ctx, page } = await backupPage(dir);
      try {
        const side = await page.evaluate((selector) => {
          const box = document.querySelector(selector).getBoundingClientRect();
          return (box.left + box.width / 2) < window.innerWidth / 2 ? 'left' : 'right';
        }, BACK_LINK);
        assert.equal(side, dir === 'rtl' ? 'left' : 'right', `wrong side in ${dir}`);
      } finally { await ctx.close(); }
    });
  }

  // The grid had no column template, so its one implicit track grew to the
  // widest child's min-content — the history tables, wider than the page once
  // the sidebar took its share. The page then hung off its start edge (found on
  // testbed-dlux in Arabic with the sidebar open). The tables already scroll in
  // their own `.dlux-table-scroll`; the track must never outgrow the page.
  for (const dir of ['ltr', 'rtl']) {
    for (const width of [1024, 800, 576]) {
      test(`no section hangs outside the page at ${width}px in ${dir}`, async () => {
        const { ctx, page } = await loggedInPage(browser);
        try {
          await page.setViewportSize({ width, height: 900 });
          await page.goto(`${BASE}/sys/backup/`, { waitUntil: 'networkidle' });
          await page.evaluate((d) => document.documentElement.setAttribute('dir', d), dir);
          const outside = await page.evaluate(() => {
            // This server has no backups, so its tables are short. Give one the
            // width a real history reaches (testbed: ~1070px of rows).
            document.querySelector('.dlux-backup-page .dlux-table-scroll table').style.minWidth = '1400px';
            const grid = document.querySelector('.dlux-backup-page');
            const box = grid.getBoundingClientRect();
            // A Bootstrap `.row` and its columns' gutter padding hang out by half
            // a gutter on purpose; the cards inside the columns must stay inside.
            return [...grid.children]
              .flatMap((child) => (child.classList.contains('row')
                ? [...child.children].flatMap((col) => [...col.children])
                : [child]))
              .filter((child) => child.getBoundingClientRect().width > 0)
              .map((child) => ({ name: String(child.className).slice(0, 40), r: child.getBoundingClientRect() }))
              .filter(({ r }) => r.left < box.left - 1 || r.right > box.right + 1)
              .map(({ name, r }) => `${name} [${Math.round(r.left)}, ${Math.round(r.right)}] in [${Math.round(box.left)}, ${Math.round(box.right)}]`);
          });
          assert.deepEqual(outside, [], 'sections stick out of the page');
        } finally { await ctx.close(); }
      });
    }
  }
});

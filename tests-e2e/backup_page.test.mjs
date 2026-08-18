// Backup and restore page layout.
//
// `.dlux-backup-page` is a CSS grid, so ANY element added as a direct child
// becomes a new row — plus the 1.35rem grid gap. Adding a Back link as a
// top-level wrapper did exactly that: it pushed the whole page down, overflowed
// the viewport and shoved the footer up over the content while scrolling.
//
// The lesson is structural, so the test is structural: the link belongs inside
// an existing cell. The grid also needs a layout boundary: without one, its
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
    // a grid row. What matters is that it sits inside the hero cell.
    const { ctx, page } = await backupPage();
    try {
      const placement = await page.evaluate(() => {
        const link = document.querySelector('.dlux-backup-back');
        const grid = document.querySelector('.dlux-backup-page');
        if (!link || !grid) return { missing: true };
        // Which direct child of the grid contains it?
        const cell = [...grid.children].find((child) => child.contains(link));
        return {
          insideHero: !!link.closest('.dlux-backup-hero'),
          cellIsHero: !!cell && cell.classList.contains('dlux-backup-hero'),
          gridRows: grid.children.length,
        };
      });
      assert.equal(placement.missing, undefined, 'the Back link is not on the page');
      assert.equal(placement.insideHero, true, 'the Back link is outside the hero');
      assert.equal(
        placement.cellIsHero, true,
        'the Back link introduced its own grid row instead of using the hero cell',
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
        const side = await page.evaluate(() => {
          const box = document.querySelector('.dlux-backup-back').getBoundingClientRect();
          return (box.left + box.width / 2) < window.innerWidth / 2 ? 'left' : 'right';
        });
        assert.equal(side, dir === 'rtl' ? 'left' : 'right', `wrong side in ${dir}`);
      } finally { await ctx.close(); }
    });
  }
});

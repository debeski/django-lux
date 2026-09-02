// ScanLink's UI, end to end.
//
// The pieces that only exist once a page is loaded: the update card must not
// appear at all while ScanLink is off (that is the whole point of the toggle),
// the releases modal must open through the dynamic-modal protocol rather than
// rendering inline, and publishing must round-trip to the manifest.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';

let server;
let browser;
let scanlinkOn = false;

async function useServer(enabled) {
  if (server && scanlinkOn === enabled) return;
  if (server) await server.stop();
  server = await startServer({ configured: true, scanlink: enabled });
  scanlinkOn = enabled;
}

before(async () => {
  browser = await chromium.launch();
}, { timeout: 120000 });

after(async () => {
  if (browser) await browser.close();
  if (server) await server.stop();
});

async function optionsPage() {
  const { ctx, page, errors } = await loggedInPage(browser);
  await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
  return { ctx, page, errors };
}

async function openReleases(page) {
  await page.evaluate(() => {
    document.documentElement.setAttribute('dir', 'ltr');
    document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
      detail: { data: { url: '/scanlink/releases/', title: 'ScanLink Releases' } },
    }));
  });
  await page.waitForSelector('[data-scanlink-releases]', { timeout: 10000 });
  await page.waitForFunction(() => Array.from(document.styleSheets).some(
    (sheet) => sheet.href?.includes('scanlink_releases.css'),
  ));
}

describe('scanlink ui', { concurrency: 1 }, () => {
  test('the update card is absent while ScanLink is off', async () => {
    await useServer(false);
    const { ctx, page } = await optionsPage();
    try {
      assert.equal(
        await page.$('[data-scanlink-update-card]'), null,
        'the card renders even though ScanLink is switched off',
      );
    } finally { await ctx.close(); }
  });

  test('no localhost-probing script is served while ScanLink is off', async () => {
    // The gate exists to stop the probe, not to hide the feature: a refused
    // connection to localhost:5443/5000 is logged by the browser itself. The
    // settings script is same-origin and carries the switch, so it must load —
    // otherwise the switch could never be turned on.
    await useServer(false);
    const { ctx, page } = await optionsPage();
    try {
      const scripts = await page.$$eval('script[src]', (els) => els.map((e) => e.src));
      assert.equal(
        scripts.some((src) => src.includes('scanlink_update.js') || src.includes('helpers/scanlink')),
        false,
        'a probing script loaded with the integration switched off',
      );
      assert.equal(
        scripts.some((src) => src.includes('scanlink_releases.js')), true,
        'the switch script must load so ScanLink can be turned on',
      );
    } finally { await ctx.close(); }
  });

  test('the update card appears once ScanLink is on', async () => {
    await useServer(true);
    const { ctx, page } = await optionsPage();
    try {
      const card = await page.$('[data-scanlink-update-card]');
      assert.ok(card, 'the card is missing with ScanLink switched on');

      // With no helper on this machine and no release published, the card must
      // still resolve to a readable state rather than sit on "Checking".
      await page.waitForTimeout(1200);
      const state = await page.evaluate(() => ({
        connection: document.querySelector('[data-scanlink-connection]')?.textContent.trim(),
        status: document.querySelector('[data-scanlink-status]')?.textContent.trim(),
      }));
      assert.notEqual(state.connection, '', 'the connection badge never resolved');
      assert.ok(state.status, 'the card never reported a status');
    } finally { await ctx.close(); }
  });

  test('the update card uses the archive status-tile layout', async () => {
    await useServer(true);
    const { ctx, page } = await optionsPage();
    try {
      const layout = await page.evaluate(() => {
        const card = document.querySelector('[data-scanlink-update-card]');
        const intro = card?.querySelector('[data-scanlink-card-intro]');
        const metrics = [...(card?.querySelectorAll('[data-scanlink-metric]') || [])];
        const boxes = metrics.map((metric) => metric.getBoundingClientRect());
        const status = card?.querySelector('[data-scanlink-status]');
        return {
          intro: intro?.textContent.trim(),
          metricCount: metrics.length,
          sameRow: boxes.length === 3 && boxes.every((box) => Math.abs(box.top - boxes[0].top) <= 2),
          equalWidths: boxes.length === 3 && boxes.every((box) => Math.abs(box.width - boxes[0].width) <= 2),
          bordered: metrics.every((metric) => getComputedStyle(metric).borderTopStyle !== 'none'),
          centered: metrics.every((metric) => getComputedStyle(metric).textAlign === 'center'),
          strongStatus: status?.classList.contains('fw-semibold'),
        };
      });
      assert.ok(layout.intro, 'the archive-style introduction is missing');
      assert.equal(layout.metricCount, 3);
      assert.equal(layout.sameRow, true);
      assert.equal(layout.equalWidths, true);
      assert.equal(layout.bordered, true);
      assert.equal(layout.centered, true);
      assert.equal(layout.strongStatus, true);
    } finally { await ctx.close(); }
  });

  test('the releases modal opens as a modal, not inline', async () => {
    await useServer(true);
    const { ctx, page } = await optionsPage();
    try {
      await page.evaluate(() => {
        document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
          detail: { data: { url: '/scanlink/releases/', title: 'ScanLink Releases' } },
        }));
      });
      await page.waitForSelector('[data-scanlink-releases]', { timeout: 10000 });

      const where = await page.evaluate(() => {
        const panel = document.querySelector('[data-scanlink-releases]');
        const modal = panel.closest('.modal');
        return { insideModal: !!modal, visible: modal ? modal.classList.contains('show') : false };
      });
      assert.equal(where.insideModal, true, 'the releases panel is not inside a modal');
      assert.equal(where.visible, true, 'the modal did not open');
    } finally { await ctx.close(); }
  });

  test('the Back link sits at the inline end in both directions', async () => {
    // Anchored with `justify-content-end`, so it lands right in English and
    // LEFT in Arabic. A physical `right` would keep it on the right in Arabic,
    // which is where the eye is least likely to look for it.
    await useServer(true);
    for (const dir of ['ltr', 'rtl']) {
      const { ctx, page } = await optionsPage();
      try {
        const result = await page.evaluate(async (direction) => {
          document.documentElement.setAttribute('dir', direction);
          document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
            detail: { data: { url: '/scanlink/releases/', title: 'ScanLink Releases' } },
          }));
          await new Promise((resolve) => setTimeout(resolve, 1500));
          const link = document.querySelector('[data-scanlink-releases] .dlux-back-link');
          if (!link) return { missing: true };
          const box = link.getBoundingClientRect();
          const host = (link.closest('.modal-body') || document.body).getBoundingClientRect();
          const icon = link.querySelector('.bi-arrow-left');
          return {
            side: (box.left + box.width / 2) < (host.left + host.width / 2) ? 'left' : 'right',
            mirrored: icon ? getComputedStyle(icon).transform !== 'none' : false,
          };
        }, dir);

        assert.equal(result.missing, undefined, 'the Back link is not in the modal');
        assert.equal(result.side, dir === 'rtl' ? 'left' : 'right', `wrong side in ${dir}`);
        assert.equal(
          result.mirrored, dir === 'rtl',
          `the arrow should mirror only in RTL, where back points the other way`,
        );
      } finally { await ctx.close(); }
    }
  });

  test('the modal uses the dlux file widget, not a hand-rolled picker', async () => {
    // Project standard: DluxFileInput everywhere, never a raw input and never a
    // second picker built beside the dlux widget.
    await useServer(true);
    const { ctx, page } = await optionsPage();
    try {
      await page.evaluate(() => {
        document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
          detail: { data: { url: '/scanlink/releases/', title: 'ScanLink Releases' } },
        }));
      });
      await page.waitForSelector('[data-scanlink-releases]', { timeout: 10000 });

      const shape = await page.evaluate(() => {
        const panel = document.querySelector('[data-scanlink-releases]');
        return {
          dluxWidgets: panel.querySelectorAll('[data-dlux-file-widget]').length,
          fileInputs: panel.querySelectorAll('input[type="file"]').length,
          dluxSwitch: panel.querySelectorAll('.dlux-settings-toggle-field').length,
          back: !!panel.querySelector('[data-dynamic-modal*="step="]'),
        };
      });
      assert.equal(shape.dluxWidgets, 1, 'the installer field is not the dlux file widget');
      assert.equal(shape.fileInputs, 1, 'expected exactly the dlux widget\'s own input');
      assert.ok(shape.dluxSwitch >= 1, 'Active is not rendered as the dlux switch');
      assert.equal(shape.back, true, 'no Back navigation to the settings step');
    } finally { await ctx.close(); }
  });

  test('the publish form keeps details compact beside the installer', async () => {
    await useServer(true);
    const { ctx, page } = await optionsPage();
    try {
      await openReleases(page);

      const desktop = await page.evaluate(() => {
        const box = (selector) => {
          const rect = document.querySelector(selector).getBoundingClientRect();
          return {
            top: rect.top, right: rect.right, bottom: rect.bottom,
            left: rect.left, width: rect.width, height: rect.height,
          };
        };
        const optionBoxes = Array.from(document.querySelectorAll(
          '.dlux-scanlink-arch-selector [data-dlux-selector-option]',
        )).map((option) => {
          const rect = option.getBoundingClientRect();
          return { top: rect.top, right: rect.right, left: rect.left };
        });
        return {
          details: box('.dlux-scanlink-release-form__details'),
          installer: box('.dlux-scanlink-release-form__installer'),
          fileCard: box('.dlux-scanlink-release-form__installer .dlux-file-card'),
          version: box('#div_id_version'),
          arch: box('#div_id_arch'),
          notes: box('#div_id_notes'),
          notesInput: box('#id_notes'),
          active: box('.dlux-settings-toggle-field'),
          submit: box('[data-scanlink-publish]'),
          publishRow: box('.dlux-scanlink-release-form__publish-row'),
          published: box('[data-scanlink-releases] h6'),
          optionBoxes,
          versionClasses: document.querySelector('#id_version').className.split(/\s+/),
          notesClasses: document.querySelector('#id_notes').className.split(/\s+/),
        };
      });

      assert.ok(Math.abs(desktop.details.top - desktop.installer.top) <= 2, 'columns do not start together');
      assert.ok(desktop.details.right <= desktop.installer.left + 2, 'installer is not beside the details in LTR');
      assert.ok(Math.abs(desktop.details.width - desktop.installer.width) <= 2, 'columns are not evenly split');
      assert.ok(
        Math.abs(desktop.details.bottom - desktop.installer.bottom) <= 2,
        'installer column does not span the details column',
      );
      assert.ok(desktop.fileCard.height > desktop.details.height * 0.65, 'file picker does not fill its column');
      assert.ok(desktop.version.top < desktop.arch.top, 'Version must precede Architecture');
      assert.ok(desktop.arch.top < desktop.active.top, 'Architecture must precede Active');
      assert.ok(
        desktop.active.height < desktop.details.height * 0.35,
        'Active stretches to the full details-column height',
      );
      assert.ok(desktop.notes.top >= desktop.details.bottom, 'Notes is still confined to the details column');
      assert.ok(desktop.notes.width > desktop.details.width, 'Notes does not stretch beyond one column');
      assert.ok(
        Math.abs(desktop.notesInput.bottom - desktop.submit.bottom) <= 2,
        'Publish is not aligned with the Notes input',
      );
      assert.ok(desktop.submit.top >= desktop.details.bottom, 'publish row is not below both columns');
      assert.ok(desktop.published.top > desktop.submit.bottom, 'published releases are not below the form');
      assert.equal(desktop.optionBoxes.length, 2, 'expected the x86 and x64 choices');
      assert.ok(
        Math.abs(desktop.optionBoxes[0].top - desktop.optionBoxes[1].top) <= 2,
        'architecture choices are stacked vertically',
      );
      assert.ok(desktop.optionBoxes[0].right <= desktop.optionBoxes[1].left, 'architecture choices overlap');
      assert.ok(desktop.versionClasses.includes('glass-input'), 'Version is missing the system input style');
      assert.ok(desktop.notesClasses.includes('glass-input'), 'Notes is missing the system input style');

      await page.setViewportSize({ width: 390, height: 844 });
      const mobile = await page.evaluate(() => {
        const details = document.querySelector('.dlux-scanlink-release-form__details').getBoundingClientRect();
        const installer = document.querySelector('.dlux-scanlink-release-form__installer').getBoundingClientRect();
        const choices = Array.from(document.querySelectorAll(
          '.dlux-scanlink-arch-selector [data-dlux-selector-option]',
        )).map((option) => option.getBoundingClientRect().top);
        const notesInput = document.querySelector('#id_notes').getBoundingClientRect();
        const submit = document.querySelector('[data-scanlink-publish]').getBoundingClientRect();
        const panel = document.querySelector('[data-scanlink-releases]');
        return {
          detailsBottom: details.bottom,
          installerTop: installer.top,
          choiceTops: choices,
          notesInputBottom: notesInput.bottom,
          submitBottom: submit.bottom,
          panelWidth: panel.clientWidth,
          panelScrollWidth: panel.scrollWidth,
        };
      });
      assert.ok(mobile.installerTop >= mobile.detailsBottom, 'mobile columns overlap instead of stacking');
      assert.ok(Math.abs(mobile.choiceTops[0] - mobile.choiceTops[1]) <= 2, 'mobile architecture choices stack');
      assert.ok(
        Math.abs(mobile.notesInputBottom - mobile.submitBottom) <= 2,
        'mobile Publish is not aligned with the Notes input',
      );
      assert.ok(mobile.panelScrollWidth <= mobile.panelWidth + 1, 'compact form causes horizontal overflow');
    } finally { await ctx.close(); }
  });
});

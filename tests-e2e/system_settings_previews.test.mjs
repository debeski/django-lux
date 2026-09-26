// System Settings previews in the Options modal.
//
// Every preview is a real page the server renders with the unsaved form. These
// tests drive what an administrator sees: the page behind the modal follows a
// change, glass mode lifts the modal off that page (and nothing of the real page
// sits above it), and each section's eye opens a real page in the popup — in the
// draft's language, with nothing saved.
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

async function optionsStep(step) {
  const { ctx, page, errors } = await loggedInPage(browser);
  await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
  await page.click(`.dlux-system-settings-tile[data-dynamic-modal*="?step=${step}"]`);
  await page.waitForSelector('#universalDynamicModal.show .dlux-system-setup-form');
  return { ctx, page, errors };
}

async function setToggle(page, name, on) {
  await page.evaluate(([n, v]) => {
    const el = document.querySelector(`#universalDynamicModal .dlux-system-setup-form [name="${n}"]`);
    if (!el) throw new Error(`toggle ${n} not found`);
    if (el.checked !== v) el.click();
  }, [name, on]);
}

// Wait until the live backdrop frame shows a page for which `probe` is true.
async function backdropWhere(page, probe) {
  await page.waitForFunction((source) => {
    const container = document.querySelector('.dlux-preview-backdrop');
    if (!container || container.hidden) return false;
    const frame = [...container.querySelectorAll('iframe')].find((f) => f.dataset.dluxPreviewStale === undefined);
    const doc = frame && frame.contentDocument;
    if (!doc || doc.readyState !== 'complete') return false;
    return new Function('doc', source)(doc);
  }, probe, { timeout: 20000 });
}

async function popupFrame(page) {
  await page.waitForSelector('.dlux-preview-popup iframe[src*="_dlux_preview="]', { timeout: 20000 });
  await page.waitForFunction(() => document.querySelector('.dlux-preview-popup__status')?.hidden === true, null, { timeout: 20000 });
  return (await page.$('.dlux-preview-popup iframe')).contentFrame();
}

async function openEye(page, target) {
  await page.evaluate((t) => {
    document.querySelector(`#universalDynamicModal [data-dlux-preview-target="${t}"]`).click();
  }, target);
  return popupFrame(page);
}

describe('Options System Settings previews', { concurrency: 1 }, () => {
  test('non-visual steps expose a clearly disabled Preview action', async () => {
    const { ctx, page, errors } = await optionsStep(2);
    try {
      const state = await page.$eval(
        '#universalDynamicModalFooter [data-dlux-system-settings-preview]',
        (button) => ({ disabled: button.disabled, mode: button.dataset.previewMode, step: button.dataset.previewStep, title: button.title }),
      );
      assert.equal(state.disabled, true);
      assert.equal(state.mode, '');
      assert.equal(state.step, 'email');
      assert.match(state.title, /not available/i);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the page behind the modal follows an unsaved titlebar change, and nothing is saved', async () => {
    const { ctx, page, errors } = await optionsStep(5);
    try {
      await setToggle(page, 'titlebar_show_title', false);
      await backdropWhere(page, "return doc.querySelector('.titlebar')?.dataset.titlebarShowTitle === 'false';");
      const realPage = await page.$eval('.titlebar', (el) => el.dataset.titlebarShowTitle);
      assert.equal(realPage, 'true', 'the real page is never patched');

      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      assert.equal(await page.$eval('.titlebar', (el) => el.dataset.titlebarShowTitle), 'true', 'leaving without saving keeps the stored value');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('opening a live step never reloads the page behind it; only a real change does', async () => {
    const requests = [];
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      page.on('request', (request) => { if (request.url().includes('_dlux_preview=')) requests.push(request.url()); });
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      await page.evaluate(() => { const main = document.getElementById('mainContent'); if (main) main.scrollTop = 400; });
      const scrolled = await page.evaluate(() => document.getElementById('mainContent')?.scrollTop || 0);
      await page.click('.dlux-system-settings-tile[data-dynamic-modal*="?step=5"]');
      await page.waitForSelector('#universalDynamicModal.show .dlux-system-setup-form');
      await page.waitForTimeout(1500);
      assert.deepEqual(requests, [], 'no copy of the page is loaded just for opening the step');
      assert.equal(await page.$('.dlux-preview-backdrop:not([hidden])'), null);

      await setToggle(page, 'titlebar_show_title', false);
      await backdropWhere(page, "return doc.querySelector('.titlebar')?.dataset.titlebarShowTitle === 'false';");
      assert.equal(requests.length, 1, 'one render for one change, never a second load of the same frame');
      const frameScroll = await page.evaluate(() => {
        const frame = [...document.querySelectorAll('.dlux-preview-backdrop iframe')].find((f) => f.dataset.dluxPreviewStale === undefined);
        return frame.contentDocument.getElementById('mainContent')?.scrollTop || 0;
      });
      assert.equal(frameScroll, scrolled, 'the copy opens at the reader\'s scroll position');

      await setToggle(page, 'titlebar_show_title', true);
      await page.waitForSelector('.dlux-preview-backdrop[hidden]', { state: 'attached', timeout: 5000 });
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('glass mode lifts the modal off the draft page, above the real chrome, and restores', async () => {
    const { ctx, page, errors } = await optionsStep(5);
    try {
      await setToggle(page, 'titlebar_show_logo', false);
      await backdropWhere(page, "return doc.querySelector('.titlebar')?.dataset.titlebarShowLogo === 'false';");
      await page.click('#universalDynamicModalFooter [data-dlux-system-settings-preview]');
      await page.waitForSelector('#universalDynamicModal.dlux-system-preview-glass');

      // The frame is pointer-events: none (elementsFromPoint skips it), so compare stacking directly.
      // Equal z-index (1050) for the titlebar, the draft frame and the modal's
      // darkening: document order decides, and it must be titlebar < frame < darkening.
      const stacking = await page.evaluate(() => {
        const z = (el) => Number(getComputedStyle(el).zIndex) || 0;
        const follows = (a, b) => Boolean(a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING);
        const container = document.querySelector('.dlux-preview-backdrop');
        const titlebar = document.querySelector('.titlebar');
        const darkening = document.querySelector('.modal-backdrop');
        return {
          visible: !container.hidden,
          sameLayer: z(container) === z(titlebar) && z(container) === z(darkening),
          coversTitlebar: follows(titlebar, container),
          darkenedByModal: follows(container, darkening),
        };
      });
      assert.deepEqual(stacking, { visible: true, sameLayer: true, coversTitlebar: true, darkenedByModal: true });

      await page.keyboard.press('Escape');
      await page.waitForSelector('#universalDynamicModal:not(.dlux-system-preview-glass)');
      assert.equal(await page.$eval('#universalDynamicModal', (el) => el.classList.contains('show')), true);

      await page.click('#universalDynamicModalFooter [data-dlux-system-settings-preview]');
      await page.waitForSelector('#universalDynamicModal.dlux-system-preview-glass');
      // The exit handlers attach a tick after entry, so the Preview click itself cannot exit.
      await page.waitForTimeout(100);
      await page.mouse.click(40, 40);
      await page.waitForSelector('#universalDynamicModal:not(.dlux-system-preview-glass)');
      assert.equal(await page.$eval('#universalDynamicModal', (el) => el.classList.contains('show')), true, 'the exit click does not reach the page');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the tables eye renders a real ribbon list page, in either language', async () => {
    const { ctx, page, errors } = await optionsStep(9);
    try {
      const frame = await openEye(page, 'sample_table');
      assert.ok(await frame.$('.dlux-ribbon'), 'a real ribbon');
      assert.ok(await frame.$('.dlux-data-table tbody tr'), 'a real DluxTable with rows');
      assert.ok(await frame.$('html[data-dlux-preview]'), 'the frame is an inert preview');

      await page.selectOption('.dlux-preview-popup [data-preview-language]', 'ar');
      await page.waitForFunction(() => document.querySelector('.dlux-preview-popup iframe')?.contentDocument?.documentElement.lang === 'ar', null, { timeout: 20000 });
      const dir = await page.evaluate(() => document.querySelector('.dlux-preview-popup iframe').contentDocument.documentElement.dir);
      assert.equal(dir, 'rtl');

      await page.keyboard.press('Escape');
      await page.waitForSelector('.dlux-preview-popup', { state: 'detached' });
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('table settings reach the sample table before they are saved', async () => {
    const { ctx, page, errors } = await optionsStep(9);
    try {
      const chosen = await page.evaluate(() => {
        const form = document.querySelector('#universalDynamicModal .dlux-system-setup-form');
        const current = form.querySelector('[name="default_table_density"]:checked')?.value;
        const other = [...form.querySelectorAll('[name="default_table_density"]')].find((el) => el.value !== current);
        other.click();
        return other.value;
      });
      const frame = await openEye(page, 'sample_table');
      const density = await frame.evaluate(() => JSON.parse(document.getElementById('user-prefs-data').textContent).table_density);
      assert.equal(density, chosen);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the modals eye opens the real dynamic modal with a form', async () => {
    const { ctx, page, errors } = await optionsStep(9);
    try {
      const frame = await openEye(page, 'sample_modal');
      await frame.waitForSelector('#universalDynamicModal.show form.dlux-form', { timeout: 20000 });
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the login step Preview renders the real login page as a visitor sees it', async () => {
    const { ctx, page, errors } = await optionsStep(11);
    try {
      assert.equal(await page.$('#universalDynamicModal [data-dlux-preview-target="login"]'), null, 'no eye: the step Preview covers it');
      await page.click('#universalDynamicModalFooter [data-dlux-system-settings-preview]');
      const frame = await popupFrame(page);
      assert.ok(await frame.$('input[name="password"]'));
      assert.equal(await frame.$('#dlux-user-dropdown-card'), null, 'no signed-in chrome');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a language default font can only be an allowed font', async () => {
    const { ctx, page, errors } = await optionsStep(4);
    try {
      const result = await page.evaluate(() => {
        const form = document.querySelector('#universalDynamicModal .dlux-system-setup-form');
        const boxes = [...form.querySelectorAll('[data-setup-font-allowed]')];
        const checked = boxes.filter((box) => box.checked);
        if (checked.length < 2) {
          boxes.filter((box) => !box.checked).slice(0, 2 - checked.length).forEach((box) => box.click());
        }
        const select = form.querySelector('.dlux-lang-font-select');
        const victim = [...form.querySelectorAll('[data-setup-font-allowed]')].find((box) => box.checked && box.getAttribute('data-setup-font-allowed') === select.value)
          || [...form.querySelectorAll('[data-setup-font-allowed]')].find((box) => box.checked);
        const slug = victim.getAttribute('data-setup-font-allowed');
        select.value = slug;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        victim.click();
        const option = [...select.options].find((o) => o.value === slug);
        return { disabled: option.disabled, moved: select.value !== slug };
      });
      assert.deepEqual(result, { disabled: true, moved: true });
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the settings modal takes the draft default font of its language', async () => {
    const { ctx, page, errors } = await optionsStep(4);
    try {
      const family = await page.evaluate(() => {
        const form = document.querySelector('#universalDynamicModal .dlux-system-setup-form');
        form.querySelectorAll('[data-setup-font-allowed]').forEach((box) => { if (!box.checked) box.click(); });
        const lang = document.documentElement.lang;
        const select = form.querySelector(`.dlux-lang-font-select[data-lang="${lang}"]`);
        const other = [...select.options].find((o) => !o.disabled && o.value !== select.value);
        select.value = other.value;
        select.dispatchEvent(new Event('change', { bubbles: true }));
        return JSON.parse(document.getElementById('dlux-font-families').textContent)[other.value];
      });
      await page.waitForFunction((f) => (document.querySelector('#universalDynamicModal').style.fontFamily || '').includes(f), family, { timeout: 20000 });
      // Closing with unsaved changes asks first; discard, as an administrator would.
      await page.keyboard.press('Escape');
      await page.click('[data-dlux-unsaved-discard]');
      await page.waitForSelector('#universalDynamicModal', { state: 'hidden' });
      await page.waitForFunction(() => !document.querySelector('#universalDynamicModal').style.fontFamily, null, { timeout: 5000 });
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('app previews need a page to render and reveal their button when registered', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      const result = await page.evaluate(() => {
        const form = document.createElement('form');
        form.dataset.dluxAppSettingsNamespace = 'tests.preview';
        form.innerHTML = '<input name="label" value="x"><button type="button" data-dlux-app-settings-preview hidden disabled>Preview</button>';
        document.body.append(form);
        let rejected = false;
        try { window.DluxSetupPreview.registerAppPreview('tests.preview', {}); } catch (error) { rejected = true; }
        const unregister = window.DluxSetupPreview.registerAppPreview('tests.preview', { path: '/' });
        const button = form.querySelector('[data-dlux-app-settings-preview]');
        const shown = !button.hidden && !button.disabled;
        unregister();
        return { rejected, shown, hiddenAgain: button.hidden };
      });
      assert.deepEqual(result, { rejected: true, shown: true, hiddenAgain: true });
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

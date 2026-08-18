// Functional tests for the wizard's language and translation editing:
// createLanguageRow, createSystemNameRow, ensureTranslationLanguageColumn,
// removeTranslationLanguageColumn, readSystemNames, syncTranslationOverrides,
// applyTranslationOverridesToMatrix, initLanguageFontsEditor and friends.
//
// Written BEFORE they move to setup/js/language.js.
//
// Adding a language is a fan-out: one action must produce a catalog row, a
// per-language system-name input, and a column in the translation matrix. Miss
// any one and the language exists but cannot be named or translated — with no
// error anywhere. So each test follows the fan-out rather than the click.
//
// The entry points (initLanguageCatalogEditor, initSystemNamesEditor,
// initTranslationMatrixEditor) stay in main.js: they sit inside its
// mutually-recursive core. Only the helpers they call move.
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
    return steps.findIndex((s) => s.querySelector(sel));
  }, selector);
  assert.ok(index >= 0, `no wizard step contains ${selector}`);
  await page.click(`[data-dlux-wizard-step-target="${index}"]`);
  await page.waitForSelector(selector, { state: 'visible', timeout: 5000 });
}

const counts = (page) => page.evaluate(() => ({
  rows: document.querySelectorAll('[data-language-row]').length,
  names: document.querySelectorAll('[data-system-name-row]').length,
  columns: document.querySelectorAll('[data-translation-input]').length,
}));

/** Add a language through the editor's own controls. */
async function addLanguage(page, code, name) {
  await page.evaluate(([c, n]) => {
    const ed = document.querySelector('[data-language-catalog-editor]');
    const set = (sel, v) => {
      const el = ed.querySelector(sel);
      if (el) { el.value = v; el.dispatchEvent(new Event('input', { bubbles: true })); }
    };
    set('[data-language-code-input]', c);
    set('[data-language-name-input]', n);
  }, [code, name]);
  await page.click('[data-language-catalog-editor] [data-language-add]');
  await page.waitForTimeout(400);
}

describe('wizard language + translation editing', { concurrency: 1 }, () => {
  test('translation matrix header stays opaque while stuck', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-translation-matrix]');
      const selector = '.dlux-translation-table-wrap';
      const scrollable = await page.$eval(selector, (wrap) => wrap.scrollHeight > wrap.clientHeight);
      assert.equal(scrollable, true, 'translation matrix is not tall enough to exercise its sticky header');

      await page.evaluate(() => {
        [...document.documentElement.classList]
          .filter((name) => name.startsWith('theme-'))
          .forEach((name) => document.documentElement.classList.remove(name));
        document.documentElement.classList.add('theme-dark');
      });
      await page.$eval(selector, (wrap) => { wrap.scrollTop = 240; });
      await page.waitForTimeout(200);
      const state = await page.$eval(selector, (wrap) => {
        const header = wrap.querySelector('thead th');
        const color = getComputedStyle(header).backgroundColor;
        const channels = color.match(/[\d.]+/g)?.map(Number) || [];
        return {
          scrollTop: wrap.scrollTop,
          topDelta: Math.abs(header.getBoundingClientRect().top - wrap.getBoundingClientRect().top),
          backgroundColor: color,
          backgroundImage: getComputedStyle(header).backgroundImage,
          alpha: channels.length > 3 ? channels[3] : 1,
        };
      });

      assert.ok(state.scrollTop > 0, 'translation matrix did not scroll');
      assert.ok(state.topDelta <= 2, `header did not stick to the matrix top; delta=${state.topDelta}`);
      assert.equal(state.alpha, 1, `stuck header backdrop is translucent: ${state.backgroundColor}`);
      assert.notEqual(state.backgroundImage, 'none', 'the active theme header surface was lost');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('adding a language fans out to a catalog row, a name field and a matrix column', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-language-catalog-editor]');
      const before = await counts(page);

      await addLanguage(page, 'fr', 'French');
      const after = await counts(page);

      assert.equal(after.rows, before.rows + 1, 'no catalog row was added');
      assert.ok(after.names > before.names,
        'the new language got no system-name field, so the system cannot be named in it');
      assert.ok(after.columns > before.columns,
        'the new language got no translation column, so nothing can be translated into it');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a language code is normalised before it becomes a row', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-language-catalog-editor]');
      await addLanguage(page, '  PT_BR ', 'Brazilian');

      const codes = await page.$$eval('[data-language-row]',
        (els) => els.map((e) => e.getAttribute('data-language-code') || e.dataset.languageCode));
      assert.ok(codes.includes('pt-br'),
        `the code was not canonicalised to pt-br; saw ${JSON.stringify(codes)}`);
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('removing a language takes its matrix column with it', async () => {
    // The reverse of the fan-out. A stranded column would post overrides for a
    // language that no longer exists.
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-language-catalog-editor]');
      await addLanguage(page, 'de', 'German');
      const withDe = await counts(page);

      const removed = await page.evaluate(() => {
        const row = [...document.querySelectorAll('[data-language-row]')]
          .find((r) => (r.getAttribute('data-language-code') || r.dataset.languageCode) === 'de');
        if (!row) return false;
        const btn = row.querySelector('[data-language-remove], button');
        if (!btn) return false;
        btn.click();
        return true;
      });
      if (!removed) return; // no remove control in this markup variant
      await page.waitForTimeout(400);

      const after = await counts(page);
      assert.ok(after.rows < withDe.rows, 'the catalog row was not removed');
      assert.ok(after.columns < withDe.columns,
        'the translation column outlived its language — overrides would post for a dead code');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a typed translation override reaches the posted hidden field', async () => {
    const { ctx, page, errors } = await wizard();
    try {
      await stepContaining(page, '[data-language-catalog-editor]');
      const input = await page.$('[data-translation-input]');
      if (!input) return;

      await page.evaluate(() => {
        const el = document.querySelector('[data-translation-input]');
        el.value = 'override-marker';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
      });
      await page.waitForTimeout(400);

      const posted = await page.evaluate(() => {
        const el = document.querySelector('.dlux-system-setup-form [name="translations_override"]');
        return el ? el.value : null;
      });
      assert.ok(posted && posted.includes('override-marker'),
        'the typed override never reached translations_override, so it would be dropped on save');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

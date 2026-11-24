// On-demand assets: what a page downloads up front, and what loads when needed.
//
// dlux/base.html used to load the System Settings editors (~490 KB of scripts),
// the guided tour and their stylesheets on every page. They are now bundles
// (dlux/lazy_assets.py) that dlux/base/js/lazy.js loads the first time their
// markup appears. These tests drive the real pages: a list page must not fetch
// them, a settings step opened in the dynamic modal must load and boot them
// (builders bound, wizard on the requested step), and all of it must still work
// under a nonce-only script-src, because injected tags only run there when they
// carry the page's nonce.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';

const ON_DEMAND = /\/static\/dlux\/(setup\/js\/|ribbon\/js\/ribbon_(builder|settings)|helpers\/(inspector|icon_picker)\/js\/|table_columns\/js\/|weather\/js\/settings|ocr\/js\/settings|tutorial\/js\/|pdf\/vendor\/)/;
const RIBBON_STEP = 8;

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

function track(page) {
  const fetched = [];
  page.on('request', (request) => {
    if (ON_DEMAND.test(new URL(request.url()).pathname)) fetched.push(new URL(request.url()).pathname);
  });
  return fetched;
}

/** Serve every page under `script-src 'nonce-…'` and nothing else. The test
 *  settings run no CSP middleware, so templates render `nonce=""`; stamp a nonce
 *  into them the way a deployment's middleware would. */
const NONCE = 'e2e-lazy-assets-nonce';
async function nonceOnlyPolicy(page, violations) {
  page.on('console', (message) => {
    if (/Content Security Policy/i.test(message.text())) violations.push(message.text());
  });
  await page.route((url) => !url.pathname.startsWith('/static/'), async (route) => {
    const response = await route.fetch();
    const type = response.headers()['content-type'] || '';
    if (!type.includes('text/html')) return route.fulfill({ response });
    const body = (await response.text()).replace(/nonce=""/g, `nonce="${NONCE}"`);
    return route.fulfill({
      response,
      body,
      headers: { ...response.headers(), 'content-security-policy': `script-src 'nonce-${NONCE}'` },
    });
  });
}

async function openRibbonStep(page) {
  await page.evaluate((step) => {
    document.body.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', {
      bubbles: true,
      detail: { data: { url: `/sys/modals/manager/dlux/SystemSettings/1/?step=${step}`, title: 'Ribbon' } },
    }));
  }, RIBBON_STEP);
  await page.waitForSelector('#universalDynamicModal.show .dlux-system-setup-form', { timeout: 10000 });
  await page.waitForFunction(() => {
    const builder = document.querySelector('#universalDynamicModal [data-ribbon-builder]');
    return builder && builder.dataset.ribbonBuilderReady === '1';
  }, null, { timeout: 10000 });
}

test('a list page loads no settings editor, tour or PDF.js script', async () => {
  const { ctx, page, errors } = await loggedInPage(browser);
  try {
    const fetched = track(page);
    await page.goto(`${BASE}/sys/users/`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(500);
    assert.deepEqual(fetched, []);
    const state = await page.evaluate(() => ({
      bootstrap: typeof window.bootstrap?.Modal,
      datepicker: typeof window.Datepicker,
      assets: typeof window.DluxAssets?.load,
      setup: typeof window.DluxSetup,
      settingsCss: !!document.querySelector('link[href*="/dlux/setup/css/main.css"]'),
    }));
    assert.deepEqual(state, {
      bootstrap: 'function', datepicker: 'function', assets: 'function', setup: 'undefined', settingsCss: false,
    });
    assert.deepEqual(errors, []);
  } finally {
    await ctx.close();
  }
});

test('a settings step opened in the dynamic modal loads and boots its editors', async () => {
  const { ctx, page, errors } = await loggedInPage(browser);
  try {
    const fetched = track(page);
    await page.goto(`${BASE}/sys/users/`, { waitUntil: 'networkidle' });
    await openRibbonStep(page);
    assert.ok(fetched.includes('/static/dlux/setup/js/main.js'));
    assert.equal(new Set(fetched).size, fetched.length, 'a bundle file was fetched twice');
    const state = await page.evaluate(() => {
      const form = document.querySelector('#universalDynamicModal .dlux-system-setup-form');
      const steps = Array.from(form.querySelectorAll('.wizard-step'));
      const lazyAnchor = document.querySelector('meta[name="dlux-lazy-styles"]');
      const settingsCss = document.querySelector('link[href*="/dlux/setup/css/main.css"]');
      const themeCss = document.querySelector('link[data-dlux-theme-css]');
      return {
        inspector: !!form.querySelector('[data-ribbon-builder] .dlux-inspector-shell, [data-ribbon-builder] [class*="dlux-inspector-shell"]'),
        visibleStep: steps.findIndex((step) => !step.classList.contains('d-none') && getComputedStyle(step).display !== 'none'),
        cssBeforeAnchor: !!settingsCss && !!(settingsCss.compareDocumentPosition(lazyAnchor) & Node.DOCUMENT_POSITION_FOLLOWING),
        cssBeforeTheme: !themeCss || !!(settingsCss.compareDocumentPosition(themeCss) & Node.DOCUMENT_POSITION_FOLLOWING),
      };
    });
    assert.equal(state.inspector, true, 'the ribbon builder booted without its inspector shell');
    assert.equal(state.visibleStep >= 0, true);
    assert.equal(state.cssBeforeAnchor, true);
    assert.equal(state.cssBeforeTheme, true);

    // A second open reuses what is loaded.
    const before = fetched.length;
    await page.keyboard.press('Escape');
    await page.waitForSelector('#universalDynamicModal.show', { state: 'detached', timeout: 5000 }).catch(() => {});
    await page.waitForTimeout(400);
    await openRibbonStep(page);
    assert.equal(fetched.length, before);
    assert.deepEqual(errors, []);
  } finally {
    await ctx.close();
  }
});

test('Options fetches the settings editors once it is idle', async () => {
  const { ctx, page, errors } = await loggedInPage(browser);
  try {
    await page.goto(`${BASE}/sys/options/`, { waitUntil: 'load' });
    await page.waitForFunction(() => typeof window.DluxSetup === 'object', null, { timeout: 10000 });
    assert.deepEqual(errors, []);
  } finally {
    await ctx.close();
  }
});

test('bundles and the tour load under a nonce-only script-src', async () => {
  const { ctx, page, errors } = await loggedInPage(browser);
  const violations = [];
  try {
    await nonceOnlyPolicy(page, violations);
    await page.goto(`${BASE}/sys/users/`, { waitUntil: 'networkidle' });
    const unsigned = await page.evaluate(() => new Promise((resolve) => {
      const script = document.createElement('script');
      script.src = '/static/dlux/sidebar/js/preload.js';
      script.addEventListener('load', () => resolve('ran'));
      script.addEventListener('error', () => resolve('blocked'));
      document.head.appendChild(script);
    }));
    assert.equal(unsigned, 'blocked', 'the policy is not in force');
    violations.length = 0;
    await openRibbonStep(page);
    await page.keyboard.press('Escape');
    await page.waitForTimeout(400);
    await page.evaluate(() => document.querySelector('[data-dlux-start-tour]').click());
    await page.waitForSelector('.driver-popover-title', { timeout: 10000 });
    const blocked = violations.filter((text) => /script/i.test(text) && /\/static\//.test(text));
    assert.deepEqual(blocked, []);
    assert.deepEqual(errors.filter((text) => !/Content Security Policy/i.test(text)), []);
  } finally {
    await ctx.close();
  }
});

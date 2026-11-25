// Superuser-editable values stay text in the screens that build markup.
//
// Sidebar builder entries, language names and scope names are stored values. A
// value such as `<img src=x onerror=…>` must reach the page as text: no element
// is created from it. The harness's nonce-only policy would block the handler on
// its own, so these tests look for the element, not just the side effect.
//
// The static guard over the same scripts is dlux/tests/test_js_html_sinks.py.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { startServer, loggedInPage, openWizard, chromium } from './server.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.join(HERE, '..', 'dlux', 'static');
const PAYLOAD = '<img src=x data-injected onerror="window.__fired=1">';

async function stepContaining(page, selector) {
  const index = await page.evaluate((sel) => {
    const steps = [...document.querySelectorAll('.wizard-step')];
    return steps.findIndex((step) => step.querySelector(sel));
  }, selector);
  assert.ok(index >= 0, `no wizard step contains ${selector}`);
  await page.click(`[data-dlux-wizard-step-target="${index}"]`);
  await page.waitForSelector(selector, { state: 'visible', timeout: 5000 });
}

const injected = (page) => page.evaluate(() => ({
  elements: document.querySelectorAll('[data-injected]').length,
  fired: Boolean(window.__fired),
}));

describe('setup builder', { concurrency: 1 }, () => {
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

  test('sidebar entries show their labels, icons and routes as text', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await openWizard(page);
      await stepContaining(page, '[data-builder-selected-tree]');
      const texts = await page.evaluate((payload) => {
        const hidden = document.querySelector('.dlux-system-setup-form [name="sidebar_config"]');
        hidden.value = JSON.stringify({
          enabled: true,
          entries: [{
            kind: 'group', id: 'g"1', label: payload, icon: `bi-x"><b data-injected>`,
            items: [{ kind: 'item', id: 'i1', url_name: payload, label: payload, icon: 'bi-1-circle' }],
          }],
        });
        hidden.dispatchEvent(new Event('change', { bubbles: true }));
        const tree = document.querySelector('[data-builder-selected-tree]');
        return [...tree.querySelectorAll('.dlux-builder-item-main span, .badge')].map((el) => el.textContent.trim());
      }, PAYLOAD);
      assert.ok(texts.filter((text) => text === PAYLOAD).length >= 3, texts.join('\n'));
      assert.deepEqual(await injected(page), { elements: 0, fired: false });
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('a new language column is headed by its name as text', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await openWizard(page);
      await stepContaining(page, '[data-language-catalog-editor]');
      await page.evaluate((payload) => {
        const editor = document.querySelector('[data-language-catalog-editor]');
        const set = (sel, value) => {
          const el = editor.querySelector(sel);
          el.value = value;
          el.dispatchEvent(new Event('input', { bubbles: true }));
        };
        set('[data-language-code-input]', 'fr');
        set('[data-language-name-input]', payload);
      }, PAYLOAD);
      await page.click('[data-language-catalog-editor] [data-language-add]');
      const header = await page.waitForSelector('[data-translation-lang-header="fr"]');
      assert.equal((await header.textContent()).trim(), `${PAYLOAD} (fr)`);
      assert.deepEqual(await injected(page), { elements: 0, fired: false });
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

describe('permissions tier preview', { concurrency: 1 }, () => {
  let server;
  let browser;
  let port;

  const escapeAttr = (value) => value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  const config = {
    scope_field_name: 'scope',
    catalog: {
      tiers: {
        scoped_staff: {
          title: PAYLOAD, description: PAYLOAD, badge_classes: 'bg-info"><b data-injected>',
          icon: 'bi-person', capabilities: [PAYLOAD],
        },
      },
      delegation_badge_label: PAYLOAD,
      warnings: {},
    },
  };
  // The scope's name arrives as an <option>'s text, which a scope manager edits.
  const PAGE = `<!doctype html><html><head><meta charset="utf-8"></head><body>
<form>
  <select name="scope"><option value="">-</option><option value="1" selected>${escapeAttr(PAYLOAD)}</option></select>
  <div class="grouped-permissions-widget">
    <input type="checkbox" name="is_staff" checked>
    <input type="checkbox" class="permission-checkbox" data-codename="manage_staff" checked>
    <div class="dlux-staff-tier-preview" data-tier-preview-config="${escapeAttr(JSON.stringify(config))}">
      <h5 class="dlux-staff-tier-preview__title"></h5>
      <p class="dlux-staff-tier-preview__description"></p>
      <div class="dlux-staff-tier-preview__badges"></div>
      <ul class="dlux-staff-tier-preview__capabilities"></ul>
      <div class="dlux-staff-tier-preview__warnings"></div>
    </div>
  </div>
</form>
<script src="/static/dlux/users/js/permissions.js"></script>
</body></html>`;

  before(async () => {
    server = http.createServer((req, res) => {
      const url = req.url.split('?')[0];
      if (url === '/') {
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end(PAGE);
        return;
      }
      const file = path.join(STATIC, url.replace(/^\/static\//, '/'));
      if (!file.startsWith(STATIC) || !fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
      res.writeHead(200, { 'Content-Type': 'application/javascript' });
      res.end(fs.readFileSync(file));
    });
    await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
    port = server.address().port;
    browser = await chromium.launch();
  });

  after(async () => {
    await browser?.close();
    await new Promise((resolve) => server.close(resolve));
  });

  test('tier, scope, badges, capabilities and warnings render as text', async () => {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', (e) => errors.push(`THROWN: ${e}`));
    try {
      await page.goto(`http://127.0.0.1:${port}/`, { waitUntil: 'networkidle' });
      await page.waitForFunction(() => document.querySelector('.dlux-staff-tier-preview__badges').children.length > 0);
      const preview = await page.evaluate(() => ({
        badges: [...document.querySelectorAll('.dlux-staff-tier-preview__badges .badge')].map((el) => el.textContent.trim()),
        capabilities: [...document.querySelectorAll('.dlux-staff-tier-preview__capabilities li')].map((el) => el.textContent),
      }));
      assert.deepEqual(preview.badges, [PAYLOAD, PAYLOAD, PAYLOAD], 'tier title, delegation and scope badges');
      assert.deepEqual(preview.capabilities, [PAYLOAD]);
      await page.waitForTimeout(200);
      assert.deepEqual(await injected(page), { elements: 0, fired: false });
      assert.deepEqual(errors, []);
    } finally { await page.close(); }
  });
});

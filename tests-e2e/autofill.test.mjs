// Guards against the browser password manager filling the titlebar search box.
//
// The bug: the global search input arrived pre-filled with a saved account
// name. Chrome does not honour autocomplete="off" when deciding what a
// "username" field is — given a password input with no username field to pair
// with, it hunts the document for the nearest plausible text input and settles
// on the first one. That was the search box.
//
// Three conditions had to hold at once, and all three did:
//   1. the search input carried a name= (a heuristic hook)
//   2. it was the first <input> in the DOM
//   3. a current-password input existed on the page with no username field
//
// (2) is a layout fact and is fine to leave alone. This file locks (1) and (3).
//
// Chrome's autofill cannot be reproduced here — Playwright starts with no saved
// credentials and the built-in manager is not scriptable — so these assert the
// conditions rather than the symptom. That is the honest limit of the test, and
// it is still enough to catch a regression: the bug cannot come back without one
// of these flipping.
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

const PAGES = ['/sys/options/', '/sys/users/', '/accounts/profile/'];

describe('password-manager autofill', { concurrency: 1 }, () => {
  test('the global search input carries no name attribute', async () => {
    // It is never submitted — search.js finds it by [data-global-search-input] —
    // so a name buys nothing and costs the heuristic.
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      for (const url of PAGES) {
        await page.goto(BASE + url, { waitUntil: 'networkidle' });
        const info = await page.evaluate(() => {
          const el = document.querySelector('[data-global-search-input]');
          if (!el) return null;
          return { name: el.getAttribute('name'), id: el.id, type: el.type };
        });
        if (!info) continue;
        assert.equal(info.name, null, `search input has name= on ${url}`);
        assert.equal(info.id, '', `search input has id= on ${url}`);
        assert.equal(info.type, 'search', `search input should stay type=search on ${url}`);
      }
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('every password field has a username field before it', async () => {
    // Pairing the password with an explicit account name is the documented fix:
    // the manager matches against that instead of scavenging the page, and it
    // also makes the confirm dialog offer the right stored credential.
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      for (const url of PAGES) {
        await page.goto(BASE + url, { waitUntil: 'networkidle' });
        const unpaired = await page.evaluate(() => {
          const inputs = [...document.querySelectorAll('input')];
          const usernameAt = inputs
            .map((el, i) => (el.getAttribute('autocomplete') === 'username' ? i : -1))
            .filter((i) => i >= 0);
          return inputs
            .map((el, i) => ({ el, i }))
            .filter(({ el }) => el.type === 'password')
            .filter(({ i }) => !usernameAt.some((u) => u < i))
            .map(({ el }) => el.id || el.name || '(anonymous)');
        });
        assert.deepEqual(
          unpaired, [],
          `${url} has password field(s) with no preceding username field: ${JSON.stringify(unpaired)}`,
        );
      }
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });

  test('the confirm-password username is the signed-in account and stays out of the way', async () => {
    const { ctx, page, errors } = await loggedInPage(browser);
    try {
      await page.goto(`${BASE}/sys/options/`, { waitUntil: 'networkidle' });
      const info = await page.evaluate(() => {
        const el = document.querySelector('#dluxConfirmUsername');
        if (!el) return null;
        return {
          value: el.value,
          readOnly: el.readOnly,
          tabIndex: el.tabIndex,
          visible: el.offsetParent !== null,
          autocomplete: el.getAttribute('autocomplete'),
        };
      });
      assert.ok(info, 'the confirm-password modal has no username field');
      assert.equal(info.autocomplete, 'username');
      assert.equal(info.value, 'visual', 'it should name the signed-in account');
      assert.equal(info.readOnly, true, 'it is context for the manager, not an editable field');
      assert.equal(info.tabIndex, -1, 'it must not appear in the tab order');
      assert.equal(info.visible, false, 'it must not be visible');
      assert.deepEqual(errors, []);
    } finally { await ctx.close(); }
  });
});

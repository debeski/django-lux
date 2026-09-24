// Every password field gets a reveal toggle, including the ones that arrive later.
//
// The helper attaches to `input[type="password"]` wherever it appears, because
// password fields come from templates, from crispy-rendered forms and from
// Django widgets, and dynamic modals insert them long after load. Driven in a
// real browser against the shipped file: the behaviour under test is DOM
// wrapping, `type` switching and caret restoration, none of which a hand-built
// fixture would prove.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.join(HERE, '..', 'dlux', 'static');
const PORT = 8741;
const BASE = `http://localhost:${PORT}`;

// `#password` carries the login page's own margins — more below than above —
// because that asymmetry is what put the eye off centre there.
const PAGE = `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/dlux/helpers/password_reveal/css/main.css">
<style>#password { display: inline-block; height: 45px; margin: 5px 0 15px; }
/* The fade is decoration, and a half-finished one reads as 0 opacity. */
.dlux-reveal__toggle { transition: none !important; }</style></head>
<body data-dlux-reveal-show="Show password" data-dlux-reveal-hide="Hide password">
<form id="login">
  <input type="text" name="username" value="ahmed">
  <input type="password" name="password" id="password" value="s3cret">
  <button type="submit">Sign in</button>
</form>
<input type="password" id="opted-out" data-dlux-no-reveal value="hidden">
<input type="password" id="empty">
<div id="later"></div>
<script src="/dlux/helpers/password_reveal/js/main.js"></script>
</body></html>`;

let server;
let browser;
let page;

/** Whether the toggle beside `selector` is actually shown (it fades, so opacity
 *  decides — Playwright's own isVisible() counts an opacity-0 element as
 *  visible). */
const offered = (selector) => page.evaluate((css) => {
  const button = document.querySelector(css).parentElement.querySelector('.dlux-reveal__toggle');
  return Number(getComputedStyle(button).opacity) > 0;
}, selector);

before(async () => {
  server = http.createServer((req, res) => {
    if (req.url === '/') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(PAGE);
      return;
    }
    const file = path.join(STATIC, req.url.split('?')[0]);
    if (!file.startsWith(STATIC) || !fs.existsSync(file)) {
      res.writeHead(404);
      res.end('not found');
      return;
    }
    const type = file.endsWith('.css') ? 'text/css' : 'application/javascript';
    res.writeHead(200, { 'Content-Type': type });
    res.end(fs.readFileSync(file));
  });
  await new Promise((resolve) => server.listen(PORT, resolve));
  browser = await chromium.launch();
  page = await browser.newPage();
  await page.goto(BASE, { waitUntil: 'networkidle' });
});

after(async () => {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
});

describe('password reveal', () => {
  test('a password field gains a toggle, and a text field does not', async () => {
    assert.equal(await page.locator('#password').evaluate((el) => el.parentElement.className), 'dlux-reveal');
    assert.equal(await page.locator('.dlux-reveal__toggle').count(), 2, 'one per password field');
    assert.equal(
      await page.locator('input[name="username"]').evaluate((el) => el.parentElement.tagName),
      'FORM',
      'a text input must be left exactly as the form rendered it',
    );
  });

  test('it is offered only while a field with something in it is in use', async () => {
    const toggle = page.locator('#password ~ .dlux-reveal__toggle');
    assert.equal(await offered('#password'), false, 'a form at rest is not a form of eyes');

    await page.locator('#empty').focus();
    assert.equal(await offered('#empty'), false, 'an empty field has nothing to reveal');
    await page.locator('#empty').fill('typed');
    assert.equal(await offered('#empty'), true);

    await page.locator('#password').focus();
    assert.equal(await offered('#password'), true);
    await page.locator('#empty').fill('');
    await page.locator('#password').blur();
    assert.equal(await offered('#password'), false);
  });

  test('a revealed field keeps its button after focus leaves it', async () => {
    // Otherwise the only way back to dots is to focus the field again.
    const toggle = page.locator('#password ~ .dlux-reveal__toggle');
    await page.locator('#password').focus();
    await toggle.click();
    await page.locator('input[name="username"]').focus();
    assert.equal(await offered('#password'), true);
    await toggle.click();
    assert.equal(await page.locator('#password').getAttribute('type'), 'password');
    await page.locator('input[name="username"]').focus();
    assert.equal(await offered('#password'), false);
  });

  test('it sits on the field\'s centre, not the wrapper\'s', async () => {
    // The input's margins are inside the wrapper, so centring on the wrapper
    // dropped the eye by half the difference — 5px low on the login page.
    await page.locator('#password').focus();
    const offset = await page.evaluate(() => {
      const input = document.getElementById('password');
      const button = input.parentElement.querySelector('.dlux-reveal__toggle');
      const a = input.getBoundingClientRect();
      const b = button.getBoundingClientRect();
      return Math.abs(((a.top + a.bottom) / 2) - ((b.top + b.bottom) / 2));
    });
    assert.ok(offset < 1, `the eye is ${offset}px off the field's centre`);
  });

  test('clicking it shows the password and says so', async () => {
    const toggle = page.locator('#password ~ .dlux-reveal__toggle');
    await page.locator('#password').focus();
    assert.equal(await page.locator('#password').getAttribute('type'), 'password');
    assert.equal(await toggle.getAttribute('aria-pressed'), 'false');
    assert.equal(await toggle.getAttribute('aria-label'), 'Show password');

    await toggle.click();
    assert.equal(await page.locator('#password').getAttribute('type'), 'text');
    assert.equal(await toggle.getAttribute('aria-pressed'), 'true');
    assert.equal(await toggle.getAttribute('aria-label'), 'Hide password');
    assert.equal(await toggle.locator('i').getAttribute('class'), 'bi bi-eye-slash');

    await toggle.click();
    assert.equal(await page.locator('#password').getAttribute('type'), 'password');
    assert.equal(await toggle.locator('i').getAttribute('class'), 'bi bi-eye');
  });

  test('the value and the caret survive the switch', async () => {
    await page.locator('#password').focus();
    await page.locator('#password').click();
    await page.locator('#password').evaluate((el) => el.setSelectionRange(2, 2));
    await page.locator('#password ~ .dlux-reveal__toggle').click();
    // Chrome puts the caret back at 0 a frame after the type change; the helper
    // re-applies it there, so read after that frame and not before.
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    const after = await page.locator('#password').evaluate((el) => ({
      value: el.value, start: el.selectionStart, focused: document.activeElement === el,
    }));
    assert.equal(after.value, 's3cret');
    assert.equal(after.start, 2, 'the caret must not jump to the end mid-correction');
    assert.equal(after.focused, true);
    await page.locator('#password ~ .dlux-reveal__toggle').click();
  });

  test('a field that opts out is left alone', async () => {
    assert.equal(
      await page.locator('#opted-out').evaluate((el) => el.parentElement.tagName),
      'BODY',
    );
  });

  test('a field added after load gets one too', async () => {
    await page.evaluate(() => {
      document.getElementById('later').innerHTML = '<input type="password" id="modal-password" value="later">';
    });
    await page.waitForSelector('#modal-password ~ .dlux-reveal__toggle');
    assert.equal(await page.locator('#modal-password').evaluate((el) => el.parentElement.className), 'dlux-reveal');
  });

  test('submitting hides a revealed password again', async () => {
    const toggle = page.locator('#password ~ .dlux-reveal__toggle');
    await page.locator('#password').focus();
    await toggle.click();
    assert.equal(await page.locator('#password').getAttribute('type'), 'text');
    await page.evaluate(() => {
      document.getElementById('login').addEventListener('submit', (event) => event.preventDefault());
      document.getElementById('login').requestSubmit();
    });
    assert.equal(
      await page.locator('#password').getAttribute('type'), 'password',
      'a re-rendered form must not leave the password on screen',
    );
  });

  test('the toggle is not a tab stop between the field and submit', async () => {
    await page.locator('#password').focus();
    await page.keyboard.press('Tab');
    assert.equal(await page.evaluate(() => document.activeElement.tagName), 'BUTTON');
    assert.equal(await page.evaluate(() => document.activeElement.type), 'submit');
  });
});

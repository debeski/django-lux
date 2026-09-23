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

const PAGE = `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/dlux/helpers/password_reveal/css/main.css"></head>
<body data-dlux-reveal-show="Show password" data-dlux-reveal-hide="Hide password">
<form id="login">
  <input type="text" name="username" value="ahmed">
  <input type="password" name="password" id="password" value="s3cret">
  <button type="submit">Sign in</button>
</form>
<input type="password" id="opted-out" data-dlux-no-reveal value="hidden">
<div id="later"></div>
<script src="/dlux/helpers/password_reveal/js/main.js"></script>
</body></html>`;

let server;
let browser;
let page;

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
    assert.equal(await page.locator('.dlux-reveal__toggle').count(), 1);
    assert.equal(
      await page.locator('input[name="username"]').evaluate((el) => el.parentElement.tagName),
      'FORM',
      'a text input must be left exactly as the form rendered it',
    );
  });

  test('clicking it shows the password and says so', async () => {
    const toggle = page.locator('#password ~ .dlux-reveal__toggle');
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
    await page.locator('#password').click();
    await page.locator('#password').evaluate((el) => el.setSelectionRange(2, 2));
    await page.locator('#password ~ .dlux-reveal__toggle').click();
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

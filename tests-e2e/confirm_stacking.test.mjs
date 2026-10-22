// The shared password prompt opened from inside another modal.
//
// Bootstrap gives every modal the same z-index, and #dluxConfirmModal sits
// earlier in base.html than the dynamic modal, so the prompt the Operations
// panel opened rendered *under* the panel: restart and recreate looked like
// they did nothing (found accepting 1.13.0b3 on testbed-dlux). The prompt now
// stacks itself when another modal is open, as the unsaved-changes prompt does.
//
// Real Bootstrap, the real partial and main.css; only the hit test is asserted.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(HERE, '..');
const STATIC = path.join(ROOT, 'dlux', 'static');
const PY = path.join(ROOT, '.venv', 'bin', 'python');
const PORT = 8744;
const BASE = `http://localhost:${PORT}`;

const PROMPT = execFileSync(PY, ['-c', `
import django; django.setup()
from types import SimpleNamespace
from django.template.loader import render_to_string
print(render_to_string('dlux/system/confirm_password_modal.html', {'request': SimpleNamespace(csp_nonce='n')}))
`], { cwd: ROOT, env: { ...process.env, DJANGO_SETTINGS_MODULE: 'dlux.tests.settings', PYTHONPATH: ROOT } }).toString();

const PAGE = `<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/bootstrap/bootstrap.min.css"><link rel="stylesheet" href="/dlux/base/css/main.css">
</head><body>
${PROMPT}
<div class="modal fade" id="universalDynamicModal" tabindex="-1">
  <div class="modal-dialog modal-lg"><div class="modal-content"><div class="modal-body">
    <p style="height:60vh">Operations panel</p>
  </div></div></div>
</div>
<script src="/bootstrap/bootstrap.bundle.min.js"></script>
<script src="/dlux/system/js/confirm_password.js"></script>
</body></html>`;

let server;
let browser;
let page;

before(async () => {
  server = http.createServer((req, res) => {
    if (req.url === '/') { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(PAGE); return; }
    const file = path.join(STATIC, req.url.split('?')[0]);
    if (!file.startsWith(STATIC) || !fs.existsSync(file)) { res.writeHead(404); res.end(); return; }
    res.writeHead(200, { 'Content-Type': file.endsWith('.css') ? 'text/css' : 'application/javascript' });
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

const shown = (selector) => page.waitForFunction((sel) => document.querySelector(sel)?.classList.contains('show'), selector);
const hidden = (selector) => page.waitForFunction((sel) => {
  const el = document.querySelector(sel);
  return el && !el.classList.contains('show') && getComputedStyle(el).display === 'none';
}, selector);

test('the prompt opened over a modal is on top and can be typed into', async () => {
  await page.evaluate(() => bootstrap.Modal.getOrCreateInstance(document.getElementById('universalDynamicModal')).show());
  await shown('#universalDynamicModal');
  await page.evaluate(() => window.dluxConfirmPassword({ title: 'Restart', requirePassword: true, onConfirm: () => true }));
  await shown('[data-dlux-confirm-modal]');
  await page.waitForTimeout(400);
  const onTop = await page.evaluate(() => {
    const input = document.querySelector('[data-dlux-confirm-password]');
    const box = input.getBoundingClientRect();
    return document.elementFromPoint(box.x + box.width / 2, box.y + box.height / 2) === input;
  });
  assert.equal(onTop, true, 'the password field is not covered by the panel or its backdrop');
  await page.locator('[data-dlux-confirm-password]').fill('pw');
  assert.equal(await page.locator('[data-dlux-confirm-password]').inputValue(), 'pw');

  await page.evaluate(() => {
    window.__promptHidden = false;
    document.querySelector('[data-dlux-confirm-modal]').addEventListener('hidden.bs.modal', () => { window.__promptHidden = true; }, { once: true });
  });
  await page.locator('[data-dlux-confirm-submit]').click();
  await page.waitForFunction(() => window.__promptHidden);
  assert.equal(await page.evaluate(() => document.querySelector('#universalDynamicModal').classList.contains('show')), true,
    'the panel underneath stays open');
  assert.equal(await page.evaluate(() => document.body.classList.contains('modal-open')), true, 'the page stays locked');
  assert.equal(await page.evaluate(() => document.body.classList.contains('dlux-modal-stacked-open')), false);
  assert.equal(await page.evaluate(() => document.querySelector('[data-dlux-confirm-modal]').classList.contains('dlux-modal-stacked')), false);
});

test('on its own the prompt does not stack', async () => {
  await page.evaluate(() => bootstrap.Modal.getInstance(document.getElementById('universalDynamicModal')).hide());
  await hidden('#universalDynamicModal');
  await page.evaluate(() => window.dluxConfirmPassword({ title: 'Sign out', requirePassword: false, onConfirm: () => true }));
  await shown('[data-dlux-confirm-modal]');
  assert.equal(await page.evaluate(() => document.querySelector('[data-dlux-confirm-modal]').classList.contains('dlux-modal-stacked')), false);
  assert.equal(await page.evaluate(() => document.body.classList.contains('dlux-modal-stacked-open')), false);
});

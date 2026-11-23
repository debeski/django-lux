// A row action of type "form" must be sent as a POST with the page's CSRF token.
//
// executeAction() checked `action.type === 'url' || action.url` first. A form action
// carries its POST target in `url`, so it was opened as a GET link: every POST-only
// view behind one answered 405 (eservices' Unpublish, Delete, Approve; the sales
// CRM's Issue invoice). submitForm() also read the token from a cookie named
// `csrftoken`, which a project renames (CSRF_COOKIE_NAME = '<project>_csrftoken').
//
// Driven against the shipped helper with the markup a table row carries; the test
// server records the method and body of every request to the action URLs.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, beforeEach, describe } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from './server.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const STATIC = path.join(HERE, '..', 'dlux', 'static');
const PORT = 8734;
const BASE = `http://localhost:${PORT}`;
const TOKEN = 'page-token-from-meta';

const ACTIONS = [
  { label: 'Unpublish', type: 'form', url: '/staff/services/54/publish/' },
  { label: 'Delete', type: 'form', url: '/staff/services/54/delete/', confirm: 'Delete it?', data: { reason: 'test' } },
  { label: 'Open', type: 'url', url: '/staff/services/54/' },
  { label: 'Legacy link', url: '/staff/services/54/legacy/' },
];

const PAGE = `<!doctype html><html><head><meta charset="utf-8">
<meta name="csrf-token" content="${TOKEN}"></head><body>
<table><tbody>
  <tr id="row" data-dlux-context data-dlux-actions='${JSON.stringify(ACTIONS)}'>
    <td>Service 54</td>
    <td><button type="button" class="dlux-row-actions-trigger" id="trigger">⋮</button></td>
  </tr>
</tbody></table>
<script src="/dlux/helpers/context_menu/js/main.js"></script>
</body></html>`;

let server;
let browser;
let page;
const requests = [];

before(async () => {
  server = http.createServer((req, res) => {
    const url = req.url.split('?')[0];
    if (url === '/' || url === '/page.html') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      return res.end(PAGE);
    }
    if (url.startsWith('/staff/')) {
      let body = '';
      req.on('data', (chunk) => { body += chunk; });
      req.on('end', () => {
        requests.push({ method: req.method, url, body: new URLSearchParams(body) });
        res.writeHead(200, { 'Content-Type': 'text/html' });
        res.end('<!doctype html><title>done</title>');
      });
      return undefined;
    }
    const file = path.join(STATIC, url);
    if (!file.startsWith(STATIC) || !fs.existsSync(file)) {
      res.writeHead(404);
      return res.end();
    }
    res.writeHead(200, { 'Content-Type': 'text/javascript' });
    return res.end(fs.readFileSync(file));
  });
  await new Promise((resolve) => server.listen(PORT, resolve));
  browser = await chromium.launch();
  page = await browser.newPage();
}, { timeout: 120000 });

after(async () => {
  if (browser) await browser.close();
  if (server) await new Promise((resolve) => server.close(resolve));
});

beforeEach(async () => {
  requests.length = 0;
  page.removeAllListeners('dialog');
  await page.goto(`${BASE}/page.html`);
});

const pick = async (label, { rightClick = false } = {}) => {
  if (rightClick) {
    await page.click('#row td', { button: 'right' });
  } else {
    await page.click('#trigger');
  }
  await page.waitForSelector('#dluxContextMenu.show');
  await page.click(`#dluxContextMenu .context-menu-item:has-text("${label}")`);
};

const nextRequest = async () => {
  for (let i = 0; i < 50 && requests.length === 0; i += 1) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  return requests[0];
};

describe('context menu row actions', () => {
  test('a form action from the three-dot trigger is a POST with the page token', async () => {
    await pick('Unpublish');
    const sent = await nextRequest();
    assert.ok(sent, 'the action sent nothing');
    assert.equal(sent.method, 'POST');
    assert.equal(sent.url, '/staff/services/54/publish/');
    assert.equal(sent.body.get('csrfmiddlewaretoken'), TOKEN);
  });

  test('a form action from a right-click is a POST too', async () => {
    await pick('Unpublish', { rightClick: true });
    const sent = await nextRequest();
    assert.equal(sent.method, 'POST');
    assert.equal(sent.body.get('csrfmiddlewaretoken'), TOKEN);
  });

  test('a confirmed form action posts its data', async () => {
    page.once('dialog', (dialog) => dialog.accept());
    await pick('Delete');
    const sent = await nextRequest();
    assert.equal(sent.method, 'POST');
    assert.equal(sent.url, '/staff/services/54/delete/');
    assert.equal(sent.body.get('reason'), 'test');
    assert.equal(sent.body.get('csrfmiddlewaretoken'), TOKEN);
  });

  test('a refused confirm sends nothing', async () => {
    page.once('dialog', (dialog) => dialog.dismiss());
    await pick('Delete');
    await new Promise((resolve) => setTimeout(resolve, 800));
    assert.deepEqual(requests, []);
    assert.ok(page.url().endsWith('/page.html'));
  });

  test('a url action still navigates with GET', async () => {
    await pick('Open');
    const sent = await nextRequest();
    assert.equal(sent.method, 'GET');
    assert.equal(sent.url, '/staff/services/54/');
  });

  test('an action with a url and no type still navigates with GET', async () => {
    await pick('Legacy link');
    const sent = await nextRequest();
    assert.equal(sent.method, 'GET');
    assert.equal(sent.url, '/staff/services/54/legacy/');
  });
});

// The Operations panel (Options > admin rail).
//
// The real template is rendered by Django once, then driven in a real browser
// with the shipped script against a stubbed state/run endpoint — the panel is
// DOM state driven by a JSON payload. dluxConfirmPassword is stubbed to accept
// with a fixed password, so each test sees exactly what would be posted.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after, describe } from 'node:test';
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
const PORT = 8743;
const BASE = `http://localhost:${PORT}`;

const PANELS = JSON.parse(execFileSync(PY, ['-c', `
import django, json; django.setup()
from types import SimpleNamespace
from django.template.loader import render_to_string
from dlux.translations import get_strings
print(json.dumps({lang: render_to_string('dlux/system/operations_panel.html',
      {'operations_enabled': True, 'request': SimpleNamespace(csp_nonce='n'), 'DLUX_STRINGS': get_strings(lang)}) for lang in ('en', 'ar')}))
`], { cwd: ROOT, env: { ...process.env, DJANGO_SETTINGS_MODULE: 'dlux.tests.settings', PYTHONPATH: ROOT } }).toString());

const PAGE = (lang) => `<!doctype html><html lang="${lang}" dir="${lang === 'ar' ? 'rtl' : 'ltr'}"><head><meta charset="utf-8"><meta name="csrf-token" content="tok">
<link rel="stylesheet" href="/static/bootstrap/bootstrap${lang === 'ar' ? '.rtl' : ''}.min.css"></head>
<body>${PANELS[lang]}</body></html>`;

const OPERATIONS = [
  ['check', 'Run deployment check', false],
  ['check-fix-apply', 'Apply repairs', true],
  ['services', 'List services', false],
  ['service-restart', 'Restart service', true],
  ['service-start', 'Start service', true],
  ['service-stop', 'Stop service', true],
  ['service-recreate', 'Recreate service', true],
  ['logs-tail', 'Show logs', false],
].map(([name, label, changes]) => ({
  name, label, changes_deployment: changes, available: true, unavailable_reason: '', panel: true,
}));

const REPAIR_CHECK = {
  token: 'c1', operation: 'check', status: 'completed', active: false, error: '',
  findings: [{ level: 'fail', name: 'maintenance-page', message: 'The proxy serves the project page.' }],
  repairs: [{ name: 'maintenance-page', files: ['.proxy/Caddyfile'], diff: '+  handle /_dlux/maintenance/*', note: '' }],
  summary: { total: 1, ok: 0, warn: 0, fail: 1 },
};

const SERVICES = {
  token: 's1', operation: 'services', status: 'completed', active: false, error: '',
  services: [
    { name: 'web', state: 'running', health: 'healthy', can_restart: true },
    { name: 'db', state: 'running', health: 'healthy', can_restart: false },
    { name: 'celery', state: 'absent', health: '', can_restart: true },
  ],
};

let server;
let browser;
let page;

// Lifecycle actions and deployment checks are separate from explicit service refreshes.
const actions = () => page.evaluate(() => window.__posted.filter((body) => body.operation !== 'services'));
const waitForAction = () => page.waitForFunction(
  () => window.__posted.some((body) => body.operation !== 'services'));

async function load(state, language = 'en') {
  await page.addInitScript((payload) => {
    window.__posted = [];
    window.__confirms = [];
    window.dluxConfirmPassword = (config) => {
      window.__confirms.push({ title: config.title, description: config.description });
      return config.onConfirm('pw-root-1234', { showError: (text) => { window.__confirmError = text; } });
    };
    const respond = (body) => Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(body) });
    window.__state = payload;
    window.fetch = (url, options) => {
      if (String(url).includes('/run')) {
        const body = {};
        (options.body || new FormData()).forEach((value, key) => { body[key] = value; });
        window.__posted.push(body);
        // The service list answers at once, as it does on a real stack in a second or two.
        const quick = body.operation === 'services';
        return respond({ ok: true, run: {
          token: `r${window.__posted.length}`, operation: body.operation,
          status: quick ? 'completed' : 'running', active: !quick,
        } });
      }
      return respond({ ok: true, ...window.__state });
    };
  }, { operations: OPERATIONS, run: null, check: null, services: null, logs: null, has_preview: false, ...state });
  await page.goto(BASE + '/?lang=' + language, { waitUntil: 'networkidle' });
  await page.waitForFunction(() => document.querySelector('[data-dlux-ops-panel]')?.dataset.bound === 'true');
}

before(async () => {
  server = http.createServer((req, res) => {
    if (req.url === '/' || req.url.startsWith('/?lang=')) {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(PAGE(new URL(req.url, BASE).searchParams.get('lang') === 'ar' ? 'ar' : 'en'));
      return;
    }
    const file = path.join(STATIC, req.url.split('?')[0].replace(/^\/static\//, '/'));
    if (!file.startsWith(STATIC) || !fs.existsSync(file)) {
      res.writeHead(404);
      res.end('not found');
      return;
    }
    res.writeHead(200, { 'Content-Type': file.endsWith('.css') ? 'text/css' : 'application/javascript' });
    res.end(fs.readFileSync(file));
  });
  await new Promise((resolve) => server.listen(PORT, resolve));
  browser = await chromium.launch();
  page = await browser.newPage();
});

after(async () => {
  await browser?.close();
  await new Promise((resolve) => server.close(resolve));
});

describe('deployment check in the panel', () => {
  test('nothing checked yet says so and offers no repair', async () => {
    await load({});
    assert.equal(await page.locator('[data-dlux-ops-panel-summary]').textContent(), 'Not checked yet');
    assert.equal(await page.locator('[data-dlux-ops-panel-apply]').isVisible(), false);
  });

  test('a check with repairs shows findings and the diff, and applying asks for the password', async () => {
    await load({ check: REPAIR_CHECK, run: REPAIR_CHECK, has_preview: true });
    assert.equal(await page.locator('[data-dlux-ops-panel-summary]').textContent(), '1 problem(s), 0 warning(s)');
    assert.equal(await page.locator('.dlux-ops-finding-message').textContent(), 'The proxy serves the project page.');
    assert.equal(await page.locator('.dlux-ops-diff').textContent(), '+  handle /_dlux/maintenance/*');
    assert.equal(await page.locator('.dlux-ops-diff').getAttribute('dir'), 'ltr', 'a diff reads left to right in Arabic too');
    assert.equal(await page.locator('.dlux-ops-finding-message').getAttribute('dir'), 'auto');
    await page.locator('[data-dlux-ops-panel-apply]').click();
    await waitForAction();
    assert.deepEqual((await actions())[0], { operation: 'check-fix-apply', current_password: 'pw-root-1234' });
  });

  test('warnings with no repair say so and offer nothing to apply', async () => {
    const warn = { ...REPAIR_CHECK, findings: [{ level: 'warn', name: 'versions', message: 'Version drift.' }],
      repairs: [], summary: { total: 1, ok: 0, warn: 1, fail: 0 } };
    await load({ check: warn, has_preview: true });
    assert.equal(await page.locator('[data-dlux-ops-panel-norepair]').textContent(),
      'No automatic repair is available for these findings.');
    assert.equal(await page.locator('[data-dlux-ops-panel-norepair]').isVisible(), true);
    assert.equal(await page.locator('[data-dlux-ops-panel-apply]').isVisible(), false);
  });

  test('a clean check says so and offers nothing', async () => {
    const clean = { ...REPAIR_CHECK, findings: [{ level: 'ok', name: 'docker', message: 'Docker daemon reachable.' }],
      repairs: [], summary: { total: 1, ok: 1, warn: 0, fail: 0 } };
    await load({ check: clean, has_preview: true });
    assert.equal(await page.locator('[data-dlux-ops-panel-summary]').textContent(), 'No problems found');
    assert.equal(await page.locator('[data-dlux-ops-panel-norepair]').isVisible(), false, 'nothing to repair, nothing to say');
    assert.equal(await page.locator('[data-dlux-ops-panel-apply]').isVisible(), false);
  });

  test('running the check asks for no password', async () => {
    await load({});
    await page.locator('[data-dlux-ops-panel-run="check"]').click();
    await waitForAction();
    assert.deepEqual((await actions())[0], { operation: 'check' });
    assert.equal(await page.evaluate(() => window.__confirms.length), 0);
  });

  test('a long check starts as a short summary and expands on request', async () => {
    const findings = Array.from({ length: 6 }, (_, index) => ({ level: 'ok', name: `n${index}`, message: `fine ${index}` }));
    await load({ check: { ...REPAIR_CHECK, findings, repairs: [], summary: { total: 6, ok: 6, warn: 0, fail: 0 } } });
    const list = page.locator('[data-dlux-ops-panel-findings]');
    const toggle = page.locator('[data-dlux-ops-panel-findings-toggle]');
    assert.equal(await toggle.textContent(), 'Show all (6)');
    const collapsed = await list.evaluate((el) => el.clientHeight);
    assert.ok(collapsed < await list.evaluate((el) => el.scrollHeight), 'collapsed hides the rest');
    await toggle.click();
    assert.equal(await toggle.textContent(), 'Show less');
    assert.ok(await list.evaluate((el) => el.clientHeight) > collapsed);
  });
});

describe('opening the panel', () => {
  test('opening and reopening cached results starts no operation', async () => {
    await load({});
    assert.equal(await page.evaluate(() => window.__posted.length), 0);
    assert.match(await page.locator('[data-dlux-ops-panel-services]').textContent(), /Refresh/);
    await load({ services: SERVICES });
    assert.equal(await page.evaluate(() => window.__posted.length), 0);
    assert.equal(await page.locator('[data-dlux-ops-panel-status]').isVisible(), false);
    await page.locator('[data-dlux-ops-panel-run="services"]').click();
    assert.deepEqual(await page.evaluate(() => window.__posted), [{operation:'services'}]);
  });

  test('an active refresh clearly explains why cached service controls are disabled', async () => {
    await load({services: SERVICES, run:{token:'refresh', operation:'services', status:'running'}});
    assert.match(await page.locator('[data-dlux-ops-panel-status]').textContent(), /List services.*Running/);
    assert.equal(await page.locator('[data-dlux-ops-panel-services] button:enabled').count(), 0);
    assert.equal(await page.locator('[data-dlux-ops-panel]').getAttribute('aria-busy'), 'true');
  });

  test('does not interrupt a run already in progress', async () => {
    await load({ run: { token: 'x', operation: 'check', status: 'running', active: true } });
    await page.waitForTimeout(300);
    assert.equal(await page.evaluate(() => window.__posted.length), 0);
  });
});

describe('services in the panel', () => {
  test('rows show state, and only allow-listed services offer restart and recreate', async () => {
    await load({ services: SERVICES });
    const rows = page.locator('[data-dlux-ops-panel-services] tr');
    assert.equal(await rows.count(), 3);
    assert.equal(await rows.nth(0).locator('td').first().textContent(), 'web');
    assert.match(await rows.nth(0).locator('td').nth(1).textContent(), /running · healthy/);
    assert.equal(await rows.nth(0).locator('button').count(), 5, 'start, stop, restart, recreate, logs');
    assert.equal(await rows.nth(0).locator('button').first().textContent(), '', 'actions are icons');
    assert.equal(await rows.nth(0).locator('button').first().getAttribute('title'), 'Start');
    assert.equal(await rows.nth(1).locator('button').count(), 1, 'a protected service only offers logs');
    assert.match(await rows.nth(1).locator('.dlux-ops-note').textContent(), /Protected/);
    assert.match(await rows.nth(2).textContent(), /not created/);
  });

  test('restart confirms with the password and names the service', async () => {
    await load({ services: SERVICES });
    await page.locator('[data-dlux-ops-panel-services] tr').first().getByRole('button', { name: /Restart/ }).click();
    await waitForAction();
    assert.deepEqual((await actions())[0],
      { operation: 'service-restart', service: 'web', current_password: 'pw-root-1234' });
    assert.match(await page.evaluate(() => window.__confirms[0].description), /web/);
  });

  test('start and stop follow service state, confirm, submit and refresh the list', async () => {
    for (const [operation, state, canStart, canStop] of [
      ['service-start', 'exited', true, false], ['service-stop', 'running', false, true],
    ]) {
      await load({ services: { ...SERVICES, services: [
        { name: 'metrics', state, can_restart: true, can_start: canStart, can_stop: canStop },
      ] } });
      const row = page.locator('[data-dlux-ops-panel-services] tr').first();
      assert.equal(await row.getByRole('button', { name: 'Start', exact: true }).isEnabled(), canStart);
      assert.equal(await row.getByRole('button', { name: 'Stop', exact: true }).isEnabled(), canStop);
      await row.getByRole('button', { name: canStart ? 'Start' : 'Stop', exact: true }).click();
      await waitForAction();
      assert.deepEqual((await actions())[0], { operation, service: 'metrics', current_password: 'pw-root-1234' });
      assert.match(await page.evaluate(() => window.__confirms[0].description), /metrics/);
      await page.evaluate(() => {
        window.__state.run = { token: `r${window.__posted.length}`, operation: window.__posted.at(-1).operation, status: 'completed', active: false };
      });
      await page.waitForFunction(() => window.__posted.filter(body => body.operation === 'services').length >= 1);
    }
  });

  test('control-path and absent services cannot be started or stopped, including on older Composer', async () => {
    await load({ services: SERVICES });
    for (const row of await page.locator('[data-dlux-ops-panel-services] tr').all()) {
      for (const name of ['Start', 'Stop']) {
        const button = row.getByRole('button', { name, exact: true });
        if (await button.count()) assert.equal(await button.isEnabled(), false);
      }
    }
    await load({ operations: OPERATIONS.map(op => op.name === 'service-stop' ? { ...op, available: false } : op),
      services: { ...SERVICES, services: [{ name: 'metrics', state: 'running', can_restart: true, can_stop: true }] } });
    assert.equal(await page.getByRole('button', { name: 'Stop', exact: true }).isEnabled(), false);
  });

  test('lifecycle controls stay translated and contained on English/Arabic desktop/mobile', async () => {
    try {
      for (const language of ['en', 'ar']) for (const width of [1440, 390]) {
        await page.setViewportSize({ width, height: 844 });
        await load({ services: { ...SERVICES, services: [
          { name: 'metrics', state: 'running', can_restart: true, can_start: false, can_stop: true },
        ] } }, language);
        const stop = language === 'ar' ? 'إيقاف' : 'Stop';
        assert.equal(await page.getByRole('button', { name: stop, exact: true }).isEnabled(), true);
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
        await page.getByRole('button', { name: stop, exact: true }).click();
        await waitForAction();
        assert.equal((await actions())[0].operation, 'service-stop');
      }
    } finally { await page.setViewportSize({ width: 1280, height: 720 }); }
  });

  test('logs need no password and render as text once the run completes', async () => {
    await load({ services: SERVICES });
    await page.locator('[data-dlux-ops-panel-services] tr').nth(1).getByRole('button', { name: /Logs/ }).click();
    await waitForAction();
    assert.deepEqual((await actions())[0], { operation: 'logs-tail', service: 'db', lines: '200' });
    await page.evaluate(() => {
      const logs = {
        token: 'r9', operation: 'logs-tail', status: 'completed', active: false, error: '',
        params: { service: 'db', lines: 200 }, logs: '<b>not html</b>\nready',
      };
      window.__state = { ...window.__state, run: logs, logs };
    });
    await page.waitForFunction(() => document.querySelector('[data-dlux-ops-panel-logs]').textContent.includes('ready'),
      null, { timeout: 5000 });
    assert.equal(await page.locator('[data-dlux-ops-panel-logs]').textContent(), '<b>not html</b>\nready');
    assert.equal(await page.locator('[data-dlux-ops-panel-logs] b').count(), 0, 'logs are text, never markup');
    assert.equal(await page.locator('[data-dlux-ops-panel-logs-title]').textContent(), 'Last 200 lines of db');
  });

  test('logs of every service load from the header icon and survive later runs', async () => {
    const logs = {
      token: 'l1', operation: 'logs-tail', status: 'completed', active: false, error: '',
      params: { lines: 200 }, logs: 'web | up\ncelery | up',
    };
    await load({ services: SERVICES, logs, run: { ...SERVICES } });
    assert.equal(await page.locator('[data-dlux-ops-panel-logs-title]').textContent(), 'Last 200 lines of all services');
    assert.equal(await page.locator('[data-dlux-ops-panel-logs]').textContent(), 'web | up\ncelery | up');
    await page.locator('[data-dlux-ops-panel-logs-all]').click();
    await waitForAction();
    assert.deepEqual((await actions())[0], { operation: 'logs-tail', lines: '200' });
    assert.equal(await page.locator('[data-dlux-ops-panel-logs]').textContent(), 'web | up\ncelery | up',
      'starting another run keeps the logs on screen');
  });

  test('an older Composer leaves the panel buttons disabled with the reason', async () => {
    const old = OPERATIONS.map((op) => (op.name === 'services'
      ? { ...op, available: false, unavailable_reason: 'This needs Composer 1.7.0b2 or later.' } : op));
    await load({ operations: old });
    const button = page.locator('[data-dlux-ops-panel-run="services"]');
    assert.equal(await button.isDisabled(), true);
    assert.equal(await button.getAttribute('title'), 'This needs Composer 1.7.0b2 or later.');
  });
});

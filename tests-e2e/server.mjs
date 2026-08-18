// Shared Django bootstrap for the functional tests.
//
// Boots a real server against a real (freshly seeded) database, because that is
// the only way to test the setup wizard honestly: its markup comes from Django
// templates and crispy-forms, so a hand-written DOM fixture would be a copy that
// drifts. Reuses settings.py / seed.py, the same pair the screenshot harness
// uses.

import { spawn, execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { chromium } from 'playwright';
import { VIEWPORT, CREDENTIALS } from './routes.mjs';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const PY = path.join(HERE, '..', '.venv', 'bin', 'python');

// node --test runs each test FILE in its own process, in parallel. A fixed port
// means the second file's server cannot bind and every test in it fails in a
// way that looks like a product bug. Derive a per-process port instead.
export const PORT = Number(process.env.E2E_PORT || (8100 + (process.pid % 700)));
export const BASE = `http://127.0.0.1:${PORT}`;

async function waitUp(timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const r = await fetch(`${BASE}/accounts/login/`);
      if (r.ok) return true;
    } catch { /* not listening yet */ }
    await new Promise((r) => setTimeout(r, 250));
  }
  return false;
}

/** Seed the database and start a server. `configured:false` leaves the setup
 *  wizard reachable — system_setup_view redirects away once it is true. */
export async function startServer({
  configured = true,
  scanlink = false,
  languageOverride = true,
  searchMode = 'icon',
} = {}) {
  const args = [path.join(HERE, 'seed.py')];
  if (!configured) args.push('--unconfigured');
  if (scanlink) args.push('--scanlink');
  if (!languageOverride) args.push('--disable-language-override');
  if (searchMode === 'always') args.push('--always-search');
  execFileSync(PY, args, { cwd: HERE, stdio: 'pipe' });

  const proc = spawn(PY, ['-m', 'django', 'runserver', String(PORT), '--noreload'], {
    cwd: HERE,
    env: { ...process.env, PYTHONPATH: `..:.`, DJANGO_SETTINGS_MODULE: 'settings' },
    stdio: 'ignore',
  });

  if (!(await waitUp())) {
    proc.kill();
    throw new Error('django server did not come up');
  }
  return {
    proc,
    async stop() {
      proc.kill();
      await new Promise((r) => proc.on('exit', r));
    },
  };
}

/** A logged-in page, plus a live list of anything the console reported. A
 *  thrown exception in the wizard leaves the page looking plausible, so every
 *  test asserts this list is empty rather than trusting the rendered output. */
export async function loggedInPage(browser) {
  const ctx = await browser.newContext({ viewport: VIEWPORT, locale: 'en-US', timezoneId: 'UTC' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(`THROWN: ${e}`));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });

  await page.goto(`${BASE}/accounts/login/`, { waitUntil: 'networkidle' });
  await page.fill('input[name="username"]', CREDENTIALS.username);
  await page.fill('input[name="password"]', CREDENTIALS.password);
  await Promise.all([
    page.waitForLoadState('networkidle'),
    page.click('button[type="submit"], input[type="submit"]'),
  ]);
  if (page.url().includes('/accounts/login/')) throw new Error('login failed');
  return { ctx, page, errors };
}

/** Open the wizard, clearing the setup-language gate that precedes it. */
export async function openWizard(page) {
  await page.goto(`${BASE}/sys/setup/`, { waitUntil: 'networkidle' });
  const gate = await page.$('.dlux-setup-language-form [data-setup-language-start]');
  if (gate) {
    await Promise.all([page.waitForLoadState('networkidle'), gate.click()]);
  }
  await page.waitForSelector('.dlux-system-setup-form', { timeout: 10000 });
}

export { chromium };

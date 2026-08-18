// Capture the theme x route matrix.
//
// Usage:  node shoot.mjs <baseline|current> [--phase main|setup] [--append]
//
// Every allowed theme's stylesheet is already present on every page (base.html
// loops DLUX_THEMES and emits a <link> for each), and the active theme is only
// a class on <html>. So one page load yields all 12 themes: set the class, wait
// for a paint, shoot. That is ~12x fewer navigations than switching the theme
// through the preference API, and it isolates the CSS from the preference
// plumbing — which is the point, since only the CSS is being refactored.

import { chromium } from 'playwright';
import { mkdir, rm } from 'node:fs/promises';
import path from 'node:path';
import { ROUTES, THEMES, VIEWPORT, BASE_URL, CREDENTIALS } from './routes.mjs';

const argv = process.argv.slice(2);
const label = argv[0];
const phaseIdx = argv.indexOf('--phase');
const phase = phaseIdx > -1 ? argv[phaseIdx + 1] : 'main';
const append = argv.includes('--append');

if (!['baseline', 'current'].includes(label)) {
  console.error('usage: node shoot.mjs <baseline|current> [--phase main|setup] [--append]');
  process.exit(2);
}

const outDir = path.join('shots', label);
if (!append) await rm(outDir, { recursive: true, force: true });
await mkdir(outDir, { recursive: true });

// Anything that moves between two runs of an unchanged page is a false diff.
// neon.css runs `scanlines 10s linear infinite` and `cyberPulse 8s infinite` on
// full-viewport overlays, so animations are removed outright rather than given
// a zero duration — a zero-duration infinite animation still resolved to a
// different frame between runs.
const FREEZE_CSS = `
  *, *::before, *::after {
    animation: none !important;
    transition: none !important;
    caret-color: transparent !important;
  }
  html { scroll-behavior: auto !important; }
`;

// The Options page renders live host stats — server clock, RAM used, uptime,
// package versions — so two runs of identical CSS never match. Rather than
// maintain a selector blocklist that silently rots as pages change, flatten
// every digit in every text node to '0'. Colour, weight, spacing and geometry
// are all still compared; only the numerals stop varying. Baseline and current
// get the identical transform, so a real regression still shows.
const NORMALIZE_DIGITS = () => {
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const p = node.parentElement;
      if (!p) return NodeFilter.FILTER_REJECT;
      const tag = p.tagName;
      if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'NOSCRIPT') return NodeFilter.FILTER_REJECT;
      return /\d/.test(node.nodeValue) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });
  const hits = [];
  while (walker.nextNode()) hits.push(walker.currentNode);
  for (const n of hits) n.nodeValue = n.nodeValue.replace(/\d/g, '0');
};

// Skia dithers gradients and positions glyphs with sub-pixel precision, and
// neither is stable run-to-run — a 141x13 gradient-filled button in the neon
// theme drifted by 100-200 pixels per run with everything else identical.
// These flags pin rasterisation to a fixed colour profile and whole-pixel text.
const browser = await chromium.launch({
  args: [
    '--force-color-profile=srgb',
    '--disable-lcd-text',
    '--disable-font-subpixel-positioning',
    '--disable-partial-raster',
    '--disable-skia-runtime-opts',
    '--force-device-scale-factor=1',
  ],
});
const CTX = {
  viewport: VIEWPORT,
  deviceScaleFactor: 1,
  reducedMotion: 'reduce',
  colorScheme: 'light',
  locale: 'en-US',
  timezoneId: 'UTC',
};

// Install the freeze stylesheet before the document renders, not after load.
// Injecting it post-load froze any transition that was already in flight at
// whatever value it had reached, which depends on timing — that showed up as a
// bimodal diff on the profile action buttons (`transition: all`): ~94px on most
// runs, ~3,500px occasionally. Blocking the transition from ever starting
// removes the race instead of sampling it.
const FREEZE_AT_START = `(() => {
  const css = ${JSON.stringify(FREEZE_CSS)};
  const add = () => {
    const s = document.createElement('style');
    s.textContent = css;
    (document.head || document.documentElement).appendChild(s);
  };
  if (document.head || document.documentElement) add();
  else document.addEventListener('readystatechange', add, { once: true });
})();`;

const ctx = await browser.newContext(CTX);
await ctx.addInitScript(FREEZE_AT_START);
const page = await ctx.newPage();

await page.goto(`${BASE_URL}/accounts/login/`, { waitUntil: 'networkidle' });
await page.fill('input[name="username"]', CREDENTIALS.username);
await page.fill('input[name="password"]', CREDENTIALS.password);
await Promise.all([
  page.waitForLoadState('networkidle'),
  page.click('button[type="submit"], input[type="submit"]'),
]);

if (page.url().includes('/accounts/login/')) {
  console.error('login failed — is the harness DB seeded? (python seed.py)');
  await browser.close();
  process.exit(1);
}

let shot = 0;
const problems = [];

for (const route of ROUTES.filter((r) => r.phase === phase)) {
  if (route.auth) {
    const resp = await page.goto(BASE_URL + route.path, { waitUntil: 'networkidle' });
    if (!(await usable(resp, route))) continue;
    await prepare(page);
    shot += await shootThemes(page, route);
  } else {
    // Logged-out pages need a context without the session cookie, or the
    // login screen just redirects to the dashboard.
    const anon = await browser.newContext(CTX);
    await anon.addInitScript(FREEZE_AT_START);
    const anonPage = await anon.newPage();
    const resp = await anonPage.goto(BASE_URL + route.path, { waitUntil: 'networkidle' });
    if (await usable(resp, route)) {
      await prepare(anonPage);
      shot += await shootThemes(anonPage, route);
    }
    await anon.close();
  }
}

async function prepare(p) {
  // `networkidle` does not imply the webfonts have been applied — a face can
  // still be swapping in when the capture fires, so text renders in the
  // fallback in one run and the real face in the next. That was the last
  // source of drift here: the page HTML and post-JS DOM were byte-identical
  // between runs while thousands of text pixels moved.
  await p.evaluate(() => document.fonts.ready);
  await p.addStyleTag({ content: FREEZE_CSS });
  await p.evaluate(NORMALIZE_DIGITS);
  // The virtual mouse stays wherever the last click left it, so whatever sits
  // under that point on the next page renders in :hover — and the submit button
  // keeps :focus across the navigation. Both are theme-styled (neon glows on
  // them), so both are cleared before capture.
  await p.mouse.move(0, 0);
  await p.evaluate(() => document.activeElement && document.activeElement.blur());
}

// A route that redirects, errors, or answers with JSON is a matrix bug, not a
// page — say so loudly instead of quietly banking a screenshot of raw JSON.
async function usable(resp, route) {
  if (!resp) { problems.push(`${route.name}: no response`); return false; }
  if (resp.status() >= 400) { problems.push(`${route.name}: HTTP ${resp.status()}`); return false; }
  const ct = (resp.headers()['content-type'] || '');
  if (!ct.includes('text/html')) { problems.push(`${route.name}: not HTML (${ct.split(';')[0]})`); return false; }
  const landed = new URL(resp.url()).pathname;
  if (landed !== route.path) { problems.push(`${route.name}: redirected to ${landed}`); return false; }
  return true;
}

async function shootThemes(p, route) {
  let n = 0;
  for (const theme of THEMES) {
    await p.evaluate((t) => {
      const root = document.documentElement;
      [...root.classList].filter((c) => c.startsWith('theme-')).forEach((c) => root.classList.remove(c));
      root.classList.add(`theme-${t}`);
    }, theme);
    // One rAF is enough with transitions frozen; it guarantees the class change
    // is through style recalc and paint before the capture.
    await p.evaluate(() => new Promise(requestAnimationFrame));

    // Deliberately NOT fullPage. Chromium builds a full-page shot by scrolling
    // and stitching, repainting `position: fixed` layers at each step — and the
    // neon theme puts two full-viewport fixed overlays on <body>. That made
    // neon the only theme that would never settle, drifting to a different
    // page on every run. The viewport is tall enough (see routes.mjs) that a
    // single unstitched capture covers these pages whole.
    await p.screenshot({ path: path.join(outDir, `${route.name}__${theme}.png`) });
    n++;
  }
  console.log(`  ${route.name.padEnd(14)} ${THEMES.length} themes`);
  return n;
}

await browser.close();
console.log(`${label}/${phase}: ${shot} screenshots -> ${outDir}`);
for (const p of problems) console.warn(`  ! ${p}`);
if (problems.length) process.exit(1);

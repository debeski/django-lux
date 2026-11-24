// Page weight: what a DjangoLux page downloads and how long its scripts run.
//
//   node page_weight.mjs [runs]        # default 5 runs per page, median reported
//
// Boots the e2e server, logs in, and loads each page with a cold cache. Bytes are
// response bodies (runserver does not compress), split by resource type, and
// include anything fetched until the network goes idle. Script and task time are
// Chromium's ScriptDuration / TaskDuration for a fresh tab up to idle; DCL and load
// are measured from the end of the HTML response.

import { startServer, loggedInPage, BASE, chromium } from './server.mjs';

const RUNS = Number(process.argv[2] || 5);
const PAGES = [
  { name: 'login', path: '/accounts/login/', auth: false },
  { name: 'users (list)', path: '/sys/users/', auth: true },
  { name: 'logs (list)', path: '/sys/logs/', auth: true },
  { name: 'options', path: '/sys/options/', auth: true },
];

const median = (xs) => {
  const s = [...xs].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)];
};

async function measure(ctx, url) {
  const page = await ctx.newPage();
  const client = await page.context().newCDPSession(page);
  await client.send('Network.enable');
  await client.send('Network.setCacheDisabled', { cacheDisabled: true });
  await client.send('Performance.enable');
  const bytes = { document: 0, script: 0, stylesheet: 0, other: 0 };
  let scripts = 0;
  const types = new Map();
  client.on('Network.responseReceived', (e) => types.set(e.requestId, e.type));
  client.on('Network.loadingFinished', (e) => {
    const t = (types.get(e.requestId) || 'Other').toLowerCase();
    const key = t in bytes ? t : 'other';
    bytes[key] += e.encodedDataLength;
    if (t === 'script') scripts += 1;
  });
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.waitForTimeout(300);
  const metrics = Object.fromEntries((await client.send('Performance.getMetrics')).metrics.map((m) => [m.name, m.value]));
  const nav = await page.evaluate(() => {
    const n = performance.getEntriesByType('navigation')[0];
    return { dcl: n.domContentLoadedEventEnd - n.responseEnd, load: n.loadEventEnd - n.responseEnd };
  });
  await client.detach();
  await page.close();
  return {
    total: bytes.document + bytes.script + bytes.stylesheet + bytes.other,
    ...bytes,
    scripts,
    scriptMs: metrics.ScriptDuration * 1000,
    taskMs: metrics.TaskDuration * 1000,
    dclMs: nav.dcl,
    loadMs: nav.load,
  };
}

const server = await startServer();
const browser = await chromium.launch();
try {
  const anon = await browser.newContext();
  const { ctx: auth, page: loginPage, errors } = await loggedInPage(browser);
  await loginPage.close();
  const rows = [];
  for (const p of PAGES) {
    const target = p.auth ? auth : anon;
    const samples = [];
    for (let i = 0; i < RUNS; i += 1) samples.push(await measure(target, `${BASE}${p.path}`));
    const pick = (k) => median(samples.map((s) => s[k]));
    rows.push({
      page: p.name,
      'total KB': (pick('total') / 1024).toFixed(1),
      'JS KB': (pick('script') / 1024).toFixed(1),
      'CSS KB': (pick('stylesheet') / 1024).toFixed(1),
      'HTML KB': (pick('document') / 1024).toFixed(1),
      scripts: pick('scripts'),
      'script ms': pick('scriptMs').toFixed(1),
      'task ms': pick('taskMs').toFixed(1),
      'DCL ms': pick('dclMs').toFixed(1),
      'load ms': pick('loadMs').toFixed(1),
    });
  }
  console.table(rows);
  if (errors.length) console.log('console errors:', errors);
} finally {
  await browser.close();
  await server.stop();
}

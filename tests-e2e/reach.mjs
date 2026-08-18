// Measure how far a two-sheet extraction could reach.
//
// A rule hoisted out of a theme file into a shared sheet changes which
// equal-specificity rules it beats:
//
//   sheet loaded AFTER the themes  -> it now beats every rule that followed it
//   sheet loaded BEFORE the themes -> it now loses to every rule that preceded it
//
// So a rule is after-safe when nothing later collides with it, and before-safe
// when nothing earlier does. "Collides" means: sets the same property AND
// actually matches at least one of the same elements. That second half cannot
// be decided from the stylesheet text — selector intersection is undecidable in
// general — so this measures it against the real DOM of the real pages, using
// the same route matrix the screenshot harness covers.
//
// Output: reach.json, {theme: {"selector||property": "after"|"before"|"both"|"neither"}}

import { chromium } from 'playwright';
import { writeFileSync } from 'node:fs';
import { ROUTES, VIEWPORT, BASE_URL, CREDENTIALS } from './routes.mjs';

const FULL = ['mono', 'dark', 'gothic', 'retro', 'neon', 'prism', 'aether'];

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: VIEWPORT, locale: 'en-US', timezoneId: 'UTC' });
const page = await ctx.newPage();

await page.goto(`${BASE_URL}/accounts/login/`, { waitUntil: 'networkidle' });
await page.fill('input[name="username"]', CREDENTIALS.username);
await page.fill('input[name="password"]', CREDENTIALS.password);
await Promise.all([
  page.waitForLoadState('networkidle'),
  page.click('button[type="submit"], input[type="submit"]'),
]);

// theme -> key -> {after:bool, before:bool}  (true = a collision exists)
const collide = {};
for (const t of FULL) collide[t] = {};

const routes = ROUTES.filter((r) => r.phase === 'main' && r.auth);

for (const route of routes) {
  const resp = await page.goto(BASE_URL + route.path, { waitUntil: 'networkidle' });
  if (!resp || resp.status() >= 400) continue;

  for (const theme of FULL) {
    await page.evaluate((th) => {
      const root = document.documentElement;
      [...root.classList].filter((c) => c.startsWith('theme-')).forEach((c) => root.classList.remove(c));
      root.classList.add(`theme-${th}`);
    }, theme);

    const found = await page.evaluate((th) => {
      const sheet = [...document.styleSheets].find(
        (s) => (s.href || '').includes(`/themes/css/${th}.css`)
      );
      if (!sheet) return null;
      let rules;
      try { rules = [...sheet.cssRules]; } catch (e) { return null; }

      // Index every element so element sets can be compared as integers.
      const els = [...document.querySelectorAll('*')];
      els.forEach((e, i) => { e.__i = i; });

      // Ordered rule table: source position, matched element set, properties.
      const table = [];
      rules.forEach((r, idx) => {
        if (!r.selectorText || !r.style || r.style.length === 0) return;
        const props = new Set();
        for (let i = 0; i < r.style.length; i++) {
          const p = r.style[i];
          if (!p.startsWith('--')) props.add(p);
        }
        if (!props.size) return;
        for (const sel of r.selectorText.split(',')) {
          const s = sel.trim();
          if (!s) continue;
          let matched;
          try { matched = new Set([...document.querySelectorAll(s)].map((e) => e.__i)); }
          catch (e) { continue; }
          if (!matched.size) continue;
          table.push({ idx, sel: s, props, matched });
        }
      });

      const norm = (s) => s
        .replace(new RegExp(`:root\\.theme-${th}\\b`, 'g'), '§')
        .replace(new RegExp(`\\.theme-${th}\\b`, 'g'), '§')
        .split(/\s+/).join(' ');

      const out = {};
      for (const a of table) {
        for (const prop of a.props) {
          const key = norm(a.sel) + '||' + prop;
          if (!out[key]) out[key] = { after: false, before: false };
          for (const b of table) {
            if (b === a || b.idx === a.idx) continue;
            if (!b.props.has(prop)) continue;
            let overlap = false;
            for (const i of a.matched) { if (b.matched.has(i)) { overlap = true; break; } }
            if (!overlap) continue;
            if (b.idx > a.idx) out[key].after = true;
            else out[key].before = true;
          }
        }
      }
      return out;
    }, theme);

    if (!found) continue;
    for (const [key, v] of Object.entries(found)) {
      const cur = collide[theme][key] || { after: false, before: false };
      collide[theme][key] = { after: cur.after || v.after, before: cur.before || v.before };
    }
  }
  console.log(`  scanned ${route.name}`);
}

await browser.close();
writeFileSync('reach.json', JSON.stringify(collide, null, 1));

// Aggregate across themes: a declaration can only be hoisted if it is safe in
// EVERY theme that declares it, since one shared rule serves all of them.
const keys = new Set();
for (const t of FULL) for (const k of Object.keys(collide[t])) keys.add(k);

let after = 0, before = 0, both = 0, neither = 0;
for (const k of keys) {
  let anyAfter = false, anyBefore = false;
  for (const t of FULL) {
    const v = collide[t][k];
    if (!v) continue;
    anyAfter = anyAfter || v.after;
    anyBefore = anyBefore || v.before;
  }
  if (!anyAfter && !anyBefore) both++;
  else if (!anyAfter) after++;
  else if (!anyBefore) before++;
  else neither++;
}
console.log('\nobserved theme declarations (selector x property), across all pages');
console.log(`  total                        : ${keys.size}`);
console.log(`  no collision either way      : ${both}    -> either sheet`);
console.log(`  safe only in the AFTER sheet : ${after}`);
console.log(`  safe only in the BEFORE sheet: ${before}`);
console.log(`  unsafe in both               : ${neither}`);
const reachable = both + after + before;
console.log(`\n  two-sheet reach: ${reachable} of ${keys.size}  (${Math.round(reachable / keys.size * 100)}%)`);
console.log(`  one-sheet reach: ${both + after} of ${keys.size}  (${Math.round((both + after) / keys.size * 100)}%)`);

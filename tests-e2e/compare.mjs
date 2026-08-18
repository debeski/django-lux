// Diff shots/current against shots/baseline.
//
// Usage:  node compare.mjs [--threshold 0.1] [--min-px 200] [--json out.json]
//
// Exit code is the point: 0 = nothing meaningful moved, 1 = something did.
// That makes it a gate around a refactor commit, not just a report.
//
// Two knobs, deliberately separate:
//
//   --threshold  per-pixel colour sensitivity (pixelmatch, 0-1, lower = stricter)
//   --min-px     how many changed pixels an image needs before it counts
//
// Skia dithers gradients, and a measured floor of ~200px of +-1/255 noise
// survives on gradient-filled controls no matter how the browser is pinned
// (srgb profile, LCD text off, sub-pixel positioning off, no stitching). The
// tempting fix is to raise --threshold until it disappears, but that blunts
// colour sensitivity everywhere — exactly what this harness exists to detect.
// So colour stays strict and the noise is absorbed by a pixel-count floor
// instead. A real theme regression is orders of magnitude larger: one wrong
// token repaints whole components, tens of thousands of pixels.
//
// The floor is calibrated, not guessed: measured noise peaks at 195px, and a
// deliberately injected regression (one --primal token in dark.css) produced
// 221px on its faintest page and 15,057px on its worst. 200 sits in that gap —
// but the gap is only 26px wide, so sub-floor diffs are always printed and
// their PNGs always written. During a refactor, look at them.

import { readdir, mkdir, writeFile } from 'node:fs/promises';
import { readFileSync, existsSync } from 'node:fs';
import path from 'node:path';
import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';

const arg = (flag, dflt) => {
  const i = process.argv.indexOf(flag);
  return i > -1 ? Number(process.argv[i + 1]) : dflt;
};
const THRESHOLD = arg('--threshold', 0.1);
const MIN_PX = arg('--min-px', 200);
const jsonIdx = process.argv.indexOf('--json');
const JSON_OUT = jsonIdx > -1 ? process.argv[jsonIdx + 1] : null;

// Per-image noise ceilings measured by calibrate.sh on this machine. Images
// absent from it are held to MIN_PX; images present are held to their own
// measured worst case plus 50% headroom. Most images never drift and stay
// strict at zero, so a real regression on them fails on the first pixel.
let NOISE = {};
if (existsSync('noise.json')) NOISE = JSON.parse(readFileSync('noise.json', 'utf8'));
const ceiling = (file) => (NOISE[file] ? Math.max(MIN_PX, Math.ceil(NOISE[file] * 1.5)) : MIN_PX);

const baseDir = path.join('shots', 'baseline');
const curDir = path.join('shots', 'current');
const diffDir = path.join('shots', 'diff');

if (!existsSync(baseDir)) { console.error('no baseline — run: ./run.sh baseline'); process.exit(2); }
if (!existsSync(curDir))  { console.error('no current  — run: ./run.sh current');  process.exit(2); }

await mkdir(diffDir, { recursive: true });

const baseShots = (await readdir(baseDir)).filter((f) => f.endsWith('.png')).sort();
const curShots = new Set((await readdir(curDir)).filter((f) => f.endsWith('.png')));

const changed = [];
const noise = [];
const missing = [];
let identical = 0;

for (const file of baseShots) {
  if (!curShots.has(file)) { missing.push(file); continue; }

  const a = PNG.sync.read(readFileSync(path.join(baseDir, file)));
  const b = PNG.sync.read(readFileSync(path.join(curDir, file)));

  // A page that changed size is already a regression; don't try to diff it.
  if (a.width !== b.width || a.height !== b.height) {
    changed.push({ file, pct: 100, note: `size ${a.width}x${a.height} -> ${b.width}x${b.height}` });
    continue;
  }

  const diff = new PNG({ width: a.width, height: a.height });
  const px = pixelmatch(a.data, b.data, diff.data, a.width, a.height, {
    threshold: THRESHOLD,
    includeAA: false,
  });

  if (px === 0) { identical++; continue; }

  const pct = (px / (a.width * a.height)) * 100;
  await writeFile(path.join(diffDir, file), PNG.sync.write(diff));
  (px < ceiling(file) ? noise : changed).push({ file, pct, px, ceil: ceiling(file) });
}

const pad = (s, n) => String(s).padEnd(n);
const row = (c) => `  ${pad(c.file.replace('.png', ''), 32)} ${pad(c.pct.toFixed(2) + '%', 9)} ${pad(c.note || c.px.toLocaleString() + ' px', 12)}${c.ceil ? ' (ceiling ' + c.ceil.toLocaleString() + ')' : ''}`;

console.log(`\n  identical            ${identical}`);
console.log(`  below noise ceiling  ${noise.length}${existsSync('noise.json') ? '   (per-image, calibrated)' : `   (< ${MIN_PX} px, UNCALIBRATED — run ./calibrate.sh)`}`);
console.log(`  CHANGED              ${changed.length}`);
if (missing.length) console.log(`  missing              ${missing.length}`);

if (noise.length) {
  console.log('\n  --- below floor, not failing ---');
  noise.sort((x, y) => y.px - x.px).forEach((c) => console.log(row(c)));
}
if (changed.length) {
  console.log('\n  --- CHANGED ---');
  console.log('  page/theme                       changed   pixels');
  changed.sort((x, y) => y.pct - x.pct).forEach((c) => console.log(row(c)));
  console.log(`\n  diffs written to ${diffDir}/`);
}
for (const m of missing) console.log(`  MISSING in current: ${m}`);

if (JSON_OUT) {
  const all = {};
  for (const f of baseShots) all[f] = 0;
  for (const c of [...noise, ...changed]) all[c.file] = c.px || 0;
  await writeFile(JSON_OUT, JSON.stringify(all, null, 1));
}

const failed = changed.length || missing.length;
console.log(failed ? '\n  FAIL\n' : '\n  PASS\n');
process.exit(failed ? 1 : 0);

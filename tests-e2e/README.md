# Browser test harness

Versioned dev tooling. `prune tests-e2e` in `MANIFEST.in` keeps it out of the wheel
and sdist, and only machine-local artefacts (`node_modules/`, `state/`, `shots/`,
`noise.json`) are gitignored,
so nothing here reaches a wheel, an sdist, CI, or the Python test suite. It is a
tool you run, not part of the package.

Two things live here: a screenshot-diff harness (`run.sh`) and functional
wizard tests (`node --test 'tests-e2e/*.test.mjs'`). They share the Django
bootstrap — `settings.py` + `seed.py` — because both need a real server against
a real database.

The screenshot harness was built to make the theme CSS de-duplication safe. That refactor touches 264
selectors shared across 7 themes, and CSS fails silently — a dropped token
renders a wrong colour, never an error. This catches that.

## Functional wizard tests

```bash
node --test --test-concurrency=1 'tests-e2e/*.test.mjs'
```

**`--test-concurrency=1` is required, not optional.** `node --test` runs each
test file in its own process in parallel, and every file's `seed.py` wipes and
rebuilds the same `state/` directory. Run them in parallel and the second file's
`before` hook dies — reported as four cancelled tests, which reads like a product
bug rather than a harness one. `npm test` inside `tests-e2e/` does this for you.

Seven tests driving a real server and a real browser, in `wizard.test.mjs`. The
setup wizard writes system configuration and stays reachable after first boot,
so a defect there misconfigures a live deployment rather than a one-off
installer — and it had no tests at all.

They cover what only shows end to end: the language gate, step navigation,
`public_root` gating its dependent fields, that submit caches the form into
sessionStorage *before* validating, that a cached state is restored on load, and
that a configured system is redirected away from the wizard. Every test also
asserts the page reported no console errors or thrown exceptions — a wizard that
throws still renders plausibly, so the screenshots alone would not catch it.

Three behaviours worth knowing, all discovered by writing these:

- State lives in **sessionStorage**, not localStorage — session-scoped on
  purpose, so it survives a reload but not a new tab.
- It is written on **submit and settings-import only**, not on keystrokes or
  step changes. A step change records the index in a dataset attribute, nothing
  more.
- Dlux switches render the real `<input>` at 0x0 behind a styled control, so
  Playwright cannot click them. `setToggle()` sets `checked` and dispatches a
  bubbling `change`, which is what a real click produces and what the wizard's
  delegated handler listens for.

## Screenshot harness

```bash
./run.sh baseline    # before touching any CSS
./calibrate.sh       # once per machine — measures rendering noise
#   ... do the refactor ...
./run.sh current     # after
./run.sh compare     # exit 0 = clean, exit 1 = something moved
```

`compare` writes an annotated PNG per mismatch to `shots/diff/`.

## What it covers

9 pages x 12 themes = 108 screenshots per run.

Pages are in `routes.mjs`. Only real HTML pages qualify — several `/sys/.../manage/`
URLs return `application/json` modal payloads that a browser renders as raw text,
identical under every theme. `shoot.mjs` rejects any route that answers non-HTML,
redirects, or errors, so one can't be added back by accident.

## Design notes

Each is load-bearing; none is incidental.

**One page load per route, not per theme.** `base.html` emits a `<link>` for
*every* allowed theme, and the active theme is only a class on `<html>`. So the
harness sets the class and re-shoots — 12x fewer navigations, and it isolates the
CSS from the theme-preference plumbing, which is the point when only CSS is
changing.

**Two phases, two databases.** `system_setup_view` redirects away from the wizard
once `SystemSettings.is_configured` is true, and `DluxMiddleware` redirects
everything else *to* the wizard while it is false. The phases cannot share a
database, so `run.sh` seeds, shoots, reseeds inverted, and shoots again.

**The database is rebuilt every run.** Pages render live counters — active
sessions, activity-log rows — that the harness increments by logging in and
browsing. Without a fresh database each run, those drift and every page reports a
phantom diff.

**Digits are flattened to `0` before capture.** The Options page renders the
server clock, RAM used, and uptime. Rather than maintain a selector blocklist
that rots, every digit in every text node becomes `0`. Colour, weight, spacing
and geometry are still compared; only numerals stop varying.

**Viewport capture, not `fullPage`.** Chromium builds a full-page shot by
scrolling and stitching, repainting `position: fixed` layers at each step —
and `neon.css` puts two full-viewport fixed overlays on `<body>` (a scanline
gradient at `z-index: 9999`, a radial glow at `-1`). That made neon the only
theme that never settled, drifting to a different page each run. The viewport is
2400px tall so these pages fit in one unstitched capture.

**Animations removed, not zeroed.** `animation: none`, because neon's
`scanlines 10s linear infinite` still resolved to different frames at
`animation-duration: 0s`.

**Mouse parked and focus cleared.** The virtual mouse stays where the last click
landed, so the next page renders whatever sits under that point in `:hover`, and
the submitted button keeps `:focus`. Both are theme-styled.

## The noise floor

Skia rasterises blurred shadows non-deterministically, and the two themes that
lean hardest on them drift between identical runs:

| theme | text-shadow | box-shadow |
|---|---|---|
| neon | 46 | 137 |
| gothic | 15 | 67 |

Three fixes were tried and rejected, each because it cost real coverage:

- **Raise `--threshold`** until the noise vanishes — blunts colour sensitivity
  on all 108 images, which is the one thing this harness exists to detect.
- **Disable shadows at capture** — blinds it to the 492 `box-shadow`
  declarations the refactor has to convert to tokens.
- **A single global pixel floor** — the floor needed to cover neon (>2,000px)
  is ten times the faintest real regression measured (221px), so it would hide
  exactly the subtle breakage worth catching.

What is used instead: `./calibrate.sh` shoots the unchanged app several times
and records the worst drift *per image*, and `compare.mjs` holds each image to
its own ceiling (measured worst case + 50% headroom). On this machine:

```
images measured : 108
never drift     : 105     <- strict at zero, fail on the first pixel
drift at all    : 3       <- profile__neon 2,177 / reports__gothic 1,449 / backup__gothic 433
```

So 105 of 108 images are maximally strict, and only the three genuinely noisy
ones are relaxed — instead of every image paying for their noise.

Re-run `./calibrate.sh` after changing the machine, the browser, or the route
matrix. **Never after changing CSS**, or you bake a regression into the ceiling.

### Verified in both directions

Not assumed — tested. Injecting one wrong token (`--primal` in `dark.css`)
against a clean baseline:

```
identical            101
CHANGED                6      <- every dark page, 221 to 15,057 px, FAIL
```

Only `dark` pages flagged, no false positives on the other 101.

### Residual flakiness — read this before trusting a red run

The per-image ceilings do **not** fully settle `neon` and `gothic`, the two
shadow-heavy themes. Observed on completely unchanged CSS:

- five consecutive calibration runs reporting **zero** drift on all 108 images
- the very next run reporting 2,258 px on `options__neon`
- and the affected images differing run to run — `options__neon` +
  `reports__gothic` one time, `profile__neon` + `options__neon` the next

So it is intermittent and non-reproducible: roughly one or two of 108 images per
run, in the range 1,500-3,500 px, always in those two themes. Everything tried
against it (source-order freeze via `addInitScript`, `document.fonts.ready`,
pinned Skia flags, no stitching, per-image ceilings) reduced it without
eliminating it.

**How to read a result, then:** a refactor regression is *systematic* — it hits
the same component across many pages with an identical or near-identical pixel
count, because one token feeds many places. That is what the phase-03 pass
caught: exactly 23 px on seven different neon pages. Noise never does that; it
lands on one or two images with unrelated magnitudes and moves around between
runs.

Judge the **shape** of a red run, not just its exit code:

| pattern | reading |
|---|---|
| same count across several pages | real, investigate |
| one or two images, only neon/gothic, moves between runs | noise |
| any palette theme (light/blue/gold/green/red) at all | real — they have no glow to be noisy |

`shots/diff/` is always written. Look at it.
## Files

| | |
|---|---|
| `run.sh` | orchestrator — seed, serve, shoot, tear down |
| `routes.mjs` | the page x theme matrix, viewport, credentials |
| `shoot.mjs` | capture; rejects non-HTML routes |
| `compare.mjs` | pixel diff, per-image ceilings, exit code |
| `calibrate.sh` | measures this machine's rendering noise -> `noise.json` |
| `settings.py` | Django settings (file-backed sqlite; the suite's is in-memory) |
| `seed.py` | rebuilds the database; `--unconfigured` for the setup phase |
| `state/` | sqlite + server log (disposable) |
| `shots/` | `baseline/`, `current/`, `diff/` |

Requires the repo's `.venv` and Node (installed via Homebrew; Chromium via
`npx playwright install chromium`).

// Options fades in like a project index: its title, cards, admin tiles and
// settings tiles carry the shared entrance (data-dlux-reveal,
// dlux/base/css/main.css), which plays once per load, does not replay when a
// card moves afterwards, and stays off under prefers-reduced-motion.
//
// Run:  node --test --test-concurrency=1 'tests-e2e/*.test.mjs'

import { test, before, after } from 'node:test';
import assert from 'node:assert/strict';
import { startServer, loggedInPage, chromium, BASE } from './server.mjs';

let server;
let browser;

before(async () => {
  server = await startServer({ configured: true });
  browser = await chromium.launch();
}, { timeout: 120000 });

after(async () => {
  if (browser) await browser.close();
  if (server) await server.stop();
});

const entrance = (page) => page.evaluate(() => {
  const name = (el) => (el ? getComputedStyle(el).animationName : null);
  const delay = (el) => (el ? getComputedStyle(el).animationDelay : null);
  const cards = [...document.querySelectorAll('#dluxOptionsGrid > *')].slice(0, 3);
  const active = document.querySelector('#dluxOptionsGrid .dlux-options-card--tab-active');
  const tabs = [...document.querySelectorAll('.dlux-options-tabs > *')].slice(0, 2);
  const tiles = [...document.querySelectorAll('.dlux-admin-settings-grid > *')].slice(0, 2);
  return {
    done: document.documentElement.classList.contains('dlux-reveal-done'),
    title: name(document.querySelector('.page-title[data-dlux-reveal]')),
    style: document.getElementById('dluxOptionsGrid').dataset.optionsStyle,
    active: active ? [name(active), delay(active)] : null,
    tabs: tabs.map(delay),
    cards: cards.map(name),
    cardDelays: cards.map(delay),
    tiles: tiles.map(name),
    tileDelays: tiles.map(delay),
  };
});

test('Options plays its entrance once as it loads', async () => {
  const { ctx, page, errors } = await loggedInPage(browser);
  try {
    await page.goto(`${BASE}/sys/options/`, { waitUntil: 'domcontentloaded' });
    const first = await entrance(page);
    assert.equal(first.done, false);
    assert.equal(first.title, 'dlux-reveal-in');
    assert.deepEqual(first.cards, ['dlux-reveal-in', 'dlux-reveal-in', 'dlux-reveal-in']);
    // The default tabbed Options: the tab strip cascades, then the shown card,
    // without the stagger the card grid layout gives the others.
    assert.equal(first.style, 'tabs');
    assert.deepEqual(first.tabs, ['0.06s', '0.1s']);
    assert.deepEqual(first.active, ['dlux-reveal-in', '0.16s']);
    assert.deepEqual(first.cardDelays.slice(1), ['0.15s', '0.22s']);
    assert.deepEqual(first.tiles, ['dlux-reveal-in', 'dlux-reveal-in']);
    assert.deepEqual(first.tileDelays, ['0.36s', '0.39s']);

    await page.waitForFunction(
      () => document.documentElement.classList.contains('dlux-reveal-done'), null, { timeout: 5000 });
    const done = await entrance(page);
    assert.equal(done.title, 'none');
    assert.deepEqual(done.cards.slice(1), ['none', 'none']);
    assert.equal(done.active[0], 'dlux-options-tab-fade', 'tab switches keep the quick tab fade');

    const moved = await page.evaluate(() => {
      const grid = document.getElementById('dluxOptionsGrid');
      const card = grid.querySelector('.dlux-options-card:not(.dlux-options-card--tab-active)');
      grid.appendChild(card);
      return getComputedStyle(card).animationName;
    });
    assert.equal(moved, 'none', 'a card moved after the entrance must not fade in again');
    assert.deepEqual(errors, []);
  } finally {
    await ctx.close();
  }
});

test('reduced motion shows Options without the entrance', async () => {
  const { ctx, page, errors } = await loggedInPage(browser);
  try {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto(`${BASE}/sys/options/`, { waitUntil: 'domcontentloaded' });
    const state = await entrance(page);
    assert.equal(state.title, 'none');
    assert.deepEqual(state.cards, ['none', 'none', 'none']);
    assert.deepEqual(state.tiles, ['none', 'none']);
    assert.equal(state.active[0], 'none');
    assert.deepEqual(errors, []);
  } finally {
    await ctx.close();
  }
});

// Unit tests for dlux/static/dlux/setup/js/builder_model.js
//
// Run:  node --test tests-js/
//
// No framework and no dependencies — node's built-in runner, and the module
// under test needs no DOM, which is exactly why it was the first slice split
// out of setup/js/main.js. Requiring the file executes its IIFE, which assigns
// the namespace onto globalThis because `window` is undefined here.
//
// These are the first JavaScript tests in the repository. setup/js/main.js is
// ~4,800 lines of permanently-reachable production surface (the wizard stays
// editable after first boot) and had none.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const require = createRequire(import.meta.url);
const here = path.dirname(fileURLToPath(import.meta.url));
// `t` in dom.js reads window.DLUX_STRINGS, so a browser-shaped global has to
// exist before these modules load. Left empty on purpose: every string then
// resolves to its hard-coded fallback, which is what the assertions expect.
globalThis.window = globalThis;
globalThis.DLUX_STRINGS = {};

// dom.js first: builder_model.js takes `t` from it, so requiring them the
// other way round throws — which is exactly how a load-order mistake in
// base.html would present at runtime.
require(path.join(here, '..', 'dlux', 'static', 'dlux', 'setup', 'js', 'dom.js'));
require(path.join(here, '..', 'dlux', 'static', 'dlux', 'setup', 'js', 'builder_model.js'));

const M = globalThis.DluxSetupModel;

test('namespace exposes the whole model', () => {
  assert.ok(M, 'DluxSetupModel not registered');
  for (const fn of [
    'normalizeLanguageCode', 'normalizeNavbarBuilderNode', 'readNavbarBuilderConfig',
    'navbarHierarchyHasNodes', 'sidebarNodeId', 'normalizeCatalog', 'buildCatalogLookup',
    'findCatalogEntry', 'cloneEntry', 'makeGroupId', 'collectSelectedItemIds',
    'findEntryLocation', 'insertEntryIntoConfig', 'topLevelItems',
  ]) {
    assert.equal(typeof M[fn], 'function', `${fn} missing`);
  }
});

test('normalizeLanguageCode canonicalises to the form the catalog is keyed by', () => {
  assert.equal(M.normalizeLanguageCode('  EN_gb '), 'en-gb');
  assert.equal(M.normalizeLanguageCode('pt_BR'), 'pt-br');
  // Anything outside [a-z0-9-] is dropped rather than escaped, so a hostile
  // value cannot smuggle a selector or separator through.
  assert.equal(M.normalizeLanguageCode('en"><script>'), 'enscript');
  assert.equal(M.normalizeLanguageCode(null), '');
  assert.equal(M.normalizeLanguageCode(undefined), '');
});

test('normalizeNavbarBuilderNode rejects anything without an id', () => {
  assert.equal(M.normalizeNavbarBuilderNode(null), null);
  assert.equal(M.normalizeNavbarBuilderNode('nope'), null);
  assert.equal(M.normalizeNavbarBuilderNode({}), null);
  assert.equal(M.normalizeNavbarBuilderNode({ id: '   ' }), null);
});

test('normalizeNavbarBuilderNode defaults kind to manual and only routes get url_name', () => {
  const manual = M.normalizeNavbarBuilderNode({ id: 'a', kind: 'whatever' });
  assert.equal(manual.kind, 'manual');
  assert.equal('url_name' in manual, false);

  const route = M.normalizeNavbarBuilderNode({ id: 'dashboard', kind: 'route' });
  assert.equal(route.kind, 'route');
  // url_name falls back to the id rather than being left undefined, so a route
  // node is always reversible.
  assert.equal(route.url_name, 'dashboard');
});

test('normalizeNavbarBuilderNode drops empty labels and normalises their codes', () => {
  const node = M.normalizeNavbarBuilderNode({
    id: 'x',
    labels: { EN_GB: ' Home ', ar: '', '': 'orphan', fr: '   ' },
  });
  assert.deepEqual(node.labels, { 'en-gb': 'Home' });
});

test('normalizeNavbarBuilderNode omits the labels key entirely when none survive', () => {
  const node = M.normalizeNavbarBuilderNode({ id: 'x', labels: { ar: '  ' } });
  assert.equal('labels' in node, false, 'an empty labels object would be serialised into the saved config');
});

test('normalizeNavbarBuilderNode recurses and prunes invalid children', () => {
  const node = M.normalizeNavbarBuilderNode({
    id: 'root',
    children: [{ id: 'ok' }, { id: '' }, null, 'junk', { id: 'deep', children: [{ id: 'leaf' }] }],
  });
  assert.deepEqual(node.children.map((c) => c.id), ['ok', 'deep']);
  assert.deepEqual(node.children[1].children.map((c) => c.id), ['leaf']);
});

test('normalizeNavbarBuilderNode tolerates a non-array children value', () => {
  assert.deepEqual(M.normalizeNavbarBuilderNode({ id: 'x', children: 'nope' }).children, []);
});

test('collectSelectedItemIds descends into groups and ignores idless entries', () => {
  const ids = M.collectSelectedItemIds([
    { kind: 'item', id: 'a' },
    { kind: 'group', id: 'g1', items: [{ kind: 'item', id: 'b' }, { kind: 'item' }] },
    { kind: 'item', id: 'c' },
  ]);
  assert.deepEqual([...ids].sort(), ['a', 'b', 'c']);
  // The group's own id is deliberately not collected — these are item ids.
  assert.equal(ids.has('g1'), false);
});

test('collectSelectedItemIds handles empty and missing input', () => {
  assert.equal(M.collectSelectedItemIds([]).size, 0);
  assert.equal(M.collectSelectedItemIds(null).size, 0);
});

test('findEntryLocation reports root vs group container', () => {
  const entries = [
    { kind: 'item', id: 'a' },
    { kind: 'group', id: 'g1', items: [{ kind: 'item', id: 'b' }] },
  ];
  const root = M.findEntryLocation(entries, 'a', 'item');
  assert.equal(root.container, 'root');
  assert.equal(root.index, 0);

  const nested = M.findEntryLocation(entries, 'b', 'item');
  assert.equal(nested.container, 'group');
  assert.equal(nested.group.id, 'g1');
  assert.equal(nested.index, 0);
});

test('findEntryLocation matches on kind as well as id', () => {
  const entries = [{ kind: 'group', id: 'dup', items: [] }, { kind: 'item', id: 'dup' }];
  assert.equal(M.findEntryLocation(entries, 'dup', 'item').entry.kind, 'item');
  assert.equal(M.findEntryLocation(entries, 'dup', 'group').entry.kind, 'group');
  assert.equal(M.findEntryLocation(entries, 'missing', 'item'), null);
});

test('insertEntryIntoConfig appends for a root container', () => {
  const cfg = [{ kind: 'item', id: 'a' }];
  M.insertEntryIntoConfig(cfg, { kind: 'item', id: 'new' }, { type: 'root-container' });
  assert.deepEqual(cfg.map((e) => e.id), ['a', 'new']);
});

test('insertEntryIntoConfig honours before/after around a root node', () => {
  const mk = () => [{ kind: 'item', id: 'a' }, { kind: 'item', id: 'b' }];
  const before = mk();
  M.insertEntryIntoConfig(before, { kind: 'item', id: 'x' },
    { type: 'root-node', targetId: 'b', targetKind: 'item', before: true });
  assert.deepEqual(before.map((e) => e.id), ['a', 'x', 'b']);

  const after = mk();
  M.insertEntryIntoConfig(after, { kind: 'item', id: 'x' },
    { type: 'root-node', targetId: 'b', targetKind: 'item', before: false });
  assert.deepEqual(after.map((e) => e.id), ['a', 'b', 'x']);
});

test('insertEntryIntoConfig falls back to the root when the target is missing', () => {
  // The drop target can disappear between drag start and drop; losing the entry
  // entirely would be data loss, so it lands at the root instead.
  const cfg = [{ kind: 'item', id: 'a' }];
  M.insertEntryIntoConfig(cfg, { kind: 'item', id: 'x' },
    { type: 'root-node', targetId: 'ghost', targetKind: 'item', before: true });
  assert.deepEqual(cfg.map((e) => e.id), ['a', 'x']);
});

test('insertEntryIntoConfig places into a group container, and falls back if the group is gone', () => {
  const cfg = [{ kind: 'group', id: 'g1', items: [] }];
  M.insertEntryIntoConfig(cfg, { kind: 'item', id: 'x' }, { type: 'group-container', groupId: 'g1' });
  assert.deepEqual(cfg[0].items.map((e) => e.id), ['x']);

  M.insertEntryIntoConfig(cfg, { kind: 'item', id: 'y' }, { type: 'group-container', groupId: 'ghost' });
  assert.deepEqual(cfg.map((e) => e.id), ['g1', 'y']);
});

test('insertEntryIntoConfig positions relative to a node inside a group', () => {
  const cfg = [{ kind: 'group', id: 'g1', items: [{ kind: 'item', id: 'a' }, { kind: 'item', id: 'b' }] }];
  M.insertEntryIntoConfig(cfg, { kind: 'item', id: 'x' },
    { type: 'group-node', parentGroupId: 'g1', targetId: 'b', targetKind: 'item', before: true });
  assert.deepEqual(cfg[0].items.map((e) => e.id), ['a', 'x', 'b']);
});

test('sidebarNodeId prefers url_name, then id, then url, then a positional fallback', () => {
  assert.equal(M.sidebarNodeId('nav', { url_name: 'home', id: 'i', url: '/u' }, 0), 'home');
  assert.equal(M.sidebarNodeId('nav', { id: 'i', url: '/u' }, 0), 'i');
  assert.equal(M.sidebarNodeId('nav', { url: '/u' }, 0), '/u');
  assert.equal(M.sidebarNodeId('nav', {}, 3), 'nav-3');
  assert.equal(M.sidebarNodeId('nav', null, 2), 'nav-2');
});

test('makeGroupId slugifies and stays unique across calls', () => {
  assert.match(M.makeGroupId('My Group!'), /^my-group-\d+-\d+$/);
  assert.match(M.makeGroupId(''), /^group-\d+-\d+$/);
  assert.match(M.makeGroupId(null), /^group-\d+-\d+$/);
  const ids = new Set(Array.from({ length: 50 }, () => M.makeGroupId('g')));
  assert.ok(ids.size > 1, 'ids must not collide wholesale within a tick');
});

test('cloneEntry returns a detached copy', () => {
  const original = { kind: 'group', id: 'g', items: [{ kind: 'item', id: 'a' }] };
  const copy = M.cloneEntry(original);
  assert.deepEqual(copy, original);
  copy.items.push({ kind: 'item', id: 'b' });
  assert.equal(original.items.length, 1, 'mutating the clone must not reach the original');
});

test('navbarHierarchyHasNodes reads the nested hierarchy, not a bare nodes list', () => {
  assert.equal(M.navbarHierarchyHasNodes({ hierarchy: { nodes: [{ id: 'a' }] } }), true);
  assert.equal(M.navbarHierarchyHasNodes({ hierarchy: { nodes: [] } }), false);
  assert.equal(M.navbarHierarchyHasNodes({ hierarchy: {} }), false);
  assert.equal(M.navbarHierarchyHasNodes({ nodes: [{ id: 'a' }] }), false);
  assert.equal(M.navbarHierarchyHasNodes({}), false);
  assert.equal(M.navbarHierarchyHasNodes(null), false);
});

test('readNavbarBuilderConfig fills a complete shape from nothing', () => {
  const cfg = M.readNavbarBuilderConfig(null);
  assert.equal(cfg.enabled, false);
  assert.equal(cfg.default_mode, 'hierarchy');
  assert.equal(cfg.allow_user_mode_override, true, 'override defaults ON — only an explicit false disables it');
  assert.deepEqual(cfg.root, { mode: 'neutral', url_name: '' });
  assert.deepEqual(cfg.hierarchy, { nodes: [] });
});

test('readNavbarBuilderConfig downgrades a route root with no url_name to neutral', () => {
  // Otherwise the navbar root would point at a route that cannot be reversed.
  const cfg = M.readNavbarBuilderConfig({ root: { mode: 'route', url_name: '   ' } });
  assert.equal(cfg.root.mode, 'neutral');
  assert.equal(cfg.root.url_name, '');

  const ok = M.readNavbarBuilderConfig({ root: { mode: 'route', url_name: ' dashboard ' } });
  assert.equal(ok.root.mode, 'route');
  assert.equal(ok.root.url_name, 'dashboard');
});

test('readNavbarBuilderConfig clamps unknown enum values to their defaults', () => {
  const cfg = M.readNavbarBuilderConfig({ root: { mode: 'banana' }, default_mode: 'banana' });
  assert.equal(cfg.root.mode, 'neutral');
  assert.equal(cfg.default_mode, 'hierarchy');
});

test('readNavbarBuilderConfig normalises nodes and drops invalid ones', () => {
  const cfg = M.readNavbarBuilderConfig({
    hierarchy: { nodes: [{ id: 'a' }, { id: '' }, null] },
  });
  assert.deepEqual(cfg.hierarchy.nodes.map((n) => n.id), ['a']);
});

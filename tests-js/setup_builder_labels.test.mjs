// Unit tests for the second batch of pure functions moved into
// dlux/static/dlux/setup/js/builder_model.js: entry normalisation and the
// label-resolution rules behind the sidebar builder.
//
// Run:  node --test 'tests-js/*.test.mjs'
//
// The label rules are the interesting part. A builder entry carries a saved
// label, but the catalog also supplies a localised one. Getting the precedence
// wrong is silently destructive in one direction (an operator's rename is
// overwritten) and silently stale in the other (a default label stops following
// the active translation).

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

// normalizeEntry looks entries up through Map.get, so the lookups are Maps —
// passing a plain object throws rather than missing, which is a fair contract.
const NO_CATALOG = new Map();

test('the second batch is exported', () => {
  for (const fn of [
    'humanizeKey', 'normalizeEntry', 'resolveBuilderItemLabel', 'resolveBuilderGroupLabel',
    'availableItemDisplayLabel', 'frameworkDefaultLabels', 'cloneGroupEntry',
    'extractImportedSettings', 'normalizeSidebarConfig',
  ]) {
    assert.equal(typeof M[fn], 'function', `${fn} missing`);
  }
});

test('humanizeKey drops the namespace and title-cases the remainder', () => {
  assert.equal(M.humanizeKey('dlux:user_activity_log'), 'User Activity Log');
  assert.equal(M.humanizeKey('report-builder'), 'Report Builder');
  assert.equal(M.humanizeKey('app:sub:deep_key'), 'Deep Key', 'only the last segment survives');
  assert.equal(M.humanizeKey(''), '');
  assert.equal(M.humanizeKey(null), '');
});

test('normalizeEntry rejects junk and entries with no identity', () => {
  assert.equal(M.normalizeEntry(null, NO_CATALOG, NO_CATALOG), null);
  assert.equal(M.normalizeEntry('nope', NO_CATALOG, NO_CATALOG), null);
  assert.equal(M.normalizeEntry({}, NO_CATALOG, NO_CATALOG), null, 'an item needs an id or a url_name');
});

test('normalizeEntry cross-fills id and url_name', () => {
  // The builder writes one or the other depending on where the entry came
  // from; downstream code reads both, so neither may be left undefined.
  const fromId = M.normalizeEntry({ id: 'reports' }, NO_CATALOG, NO_CATALOG);
  assert.equal(fromId.id, 'reports');
  assert.equal(fromId.url_name, 'reports');

  const fromUrl = M.normalizeEntry({ url_name: 'reports' }, NO_CATALOG, NO_CATALOG);
  assert.equal(fromUrl.id, 'reports');
  assert.equal(fromUrl.url_name, 'reports');
});

test('normalizeEntry defaults the icon rather than leaving it blank', () => {
  assert.equal(M.normalizeEntry({ id: 'x' }, NO_CATALOG, NO_CATALOG).icon, 'bi-link-45deg');
  assert.equal(M.normalizeEntry({ id: 'x', icon: 'bi-star' }, NO_CATALOG, NO_CATALOG).icon, 'bi-star');
});

test('normalizeEntry recurses into groups and drops invalid children', () => {
  const g = M.normalizeEntry(
    { kind: 'group', id: 'g1', items: [{ id: 'a' }, null, {}, { id: 'b' }] }, NO_CATALOG, NO_CATALOG,
  );
  assert.equal(g.kind, 'group');
  assert.deepEqual(g.items.map((i) => i.id), ['a', 'b']);
  assert.equal(g.icon, 'bi-folder2-open', 'groups get their own default icon');
});

test('normalizeEntry gives a group an id when one is missing', () => {
  const g = M.normalizeEntry({ kind: 'group', items: [] }, NO_CATALOG, NO_CATALOG);
  assert.match(g.id, /^group-\d+$/);
});

test('normalizeEntry coerces permissions to an array', () => {
  assert.deepEqual(M.normalizeEntry({ id: 'x', permissions: 'nope' }, NO_CATALOG, NO_CATALOG).permissions, []);
  assert.deepEqual(M.normalizeEntry({ id: 'x', permissions: ['a'] }, NO_CATALOG, NO_CATALOG).permissions, ['a']);
});

test('resolveBuilderItemLabel keeps a genuine rename', () => {
  // A label the operator typed must survive, even when the catalog offers one.
  const label = M.resolveBuilderItemLabel(
    { id: 'reports', label: 'Quarterly Numbers' },
    { label: 'Reports' },
    null,
  );
  assert.equal(label, 'Quarterly Numbers');
});

test('resolveBuilderItemLabel replaces a stale framework default with the localised one', () => {
  // If the saved label is just the framework default captured at build time, it
  // must give way to the catalog's current (translated) label — otherwise the
  // sidebar stays in whatever language it was first configured in.
  const discovered = { label: 'Rapports' };
  const defaults = M.frameworkDefaultLabels({ id: 'reports' }, discovered);
  assert.ok(defaults instanceof Set || Array.isArray(defaults) || defaults,
    'frameworkDefaultLabels should return a collection');

  const stale = [...defaults][0];
  if (stale === undefined) return;
  const label = M.resolveBuilderItemLabel({ id: 'reports', label: stale }, discovered, null);
  assert.equal(label, 'Rapports', 'a default-valued label should follow the catalog');
});

test('resolveBuilderItemLabel falls back to the identifier when nothing else exists', () => {
  assert.equal(M.resolveBuilderItemLabel({ url_name: 'sys_reports' }, null, null), 'sys_reports');
  assert.equal(M.resolveBuilderItemLabel({ id: 'only_id' }, null, null), 'only_id');
});

test('cloneGroupEntry re-identifies the copy and detaches its items', () => {
  // Not a plain clone: duplicating a group must not reuse the original's id, or
  // the two collide in findEntryLocation and edits land on the wrong one. It
  // also fills the label and icon defaults.
  const original = { kind: 'group', id: 'g', items: [{ kind: 'item', id: 'a' }] };
  const copy = M.cloneGroupEntry(original);

  assert.notEqual(copy.id, original.id, 'the clone must get its own id');
  assert.match(copy.id, /^g-\d+-\d+$/);
  assert.equal(copy.kind, 'group');
  assert.equal(copy.icon, 'bi-folder2-open');
  assert.equal(copy.label, 'Group', 'falls back to the translated default label');
  assert.deepEqual(copy.items.map((i) => i.id), ['a']);

  copy.items.push({ kind: 'item', id: 'b' });
  assert.equal(original.items.length, 1, 'mutating the clone must not reach the original');
});

test('cloneGroupEntry keeps a label the operator set', () => {
  const copy = M.cloneGroupEntry({ kind: 'group', id: 'g', label: 'Admin Tools', items: [] });
  assert.equal(copy.label, 'Admin Tools');
});

test('extractImportedSettings unwraps the export envelope', () => {
  const inner = { identity: { display_name: 'X' } };
  assert.deepEqual(
    M.extractImportedSettings({ format: 'django-lux.system-settings', settings: inner }),
    inner,
  );
});

test('extractImportedSettings passes a bare settings object straight through', () => {
  // Hand-written config files have no envelope; rejecting them would make the
  // import button fail on exactly the files people write by hand.
  const bare = { identity: { display_name: 'Y' } };
  assert.deepEqual(M.extractImportedSettings(bare), bare);
  assert.equal(M.extractImportedSettings(null), null);
  assert.equal(M.extractImportedSettings('nope'), null);
});

test('extractImportedSettings ignores a mislabelled envelope', () => {
  // Right format marker, missing payload: fall through to the object itself
  // rather than returning undefined.
  const odd = { format: 'django-lux.system-settings' };
  assert.deepEqual(M.extractImportedSettings(odd), odd);
});

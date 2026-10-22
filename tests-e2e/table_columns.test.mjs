import {test, before, after} from 'node:test';
import assert from 'node:assert/strict';
import {startServer, loggedInPage, chromium, BASE} from './server.mjs';

let server;
let browser;
before(async () => {
  server = await startServer({configured: true});
  browser = await chromium.launch();
}, {timeout: 120000});
after(async () => {
  await browser?.close();
  await server?.stop();
});

async function openTables(page, {showSystem = true} = {}) {
  await page.goto(`${BASE}/sys/options/`, {waitUntil: 'networkidle'});
  await page.locator('[data-dlux-settings-step="tables"]').click();
  await page.waitForSelector('#universalDynamicModal.show [data-table-column-builder][data-table-columns-ready="1"]');
  if (showSystem) await page.locator('#universalDynamicModal [data-table-columns-system-toggle]').check();
  return page.locator('#universalDynamicModal [data-table-model="auth.user"]');
}

test('system tables are opt-in and filtering never edits or discards their configuration', async () => {
  const {ctx, page, errors} = await loggedInPage(browser);
  try {
    let model = await openTables(page, {showSystem:false});
    const root = page.locator('#universalDynamicModal [data-table-column-builder]');
    const toggle = root.locator('[data-table-columns-system-toggle]');
    const hidden = page.locator('#universalDynamicModal [name="tables_config"]');
    const before = await hidden.inputValue();
    const catalog = await root.evaluate(node => JSON.parse(node.dataset.catalog));
    const systems = catalog.filter(entry => entry.is_system).map(entry => entry.key);
    assert.ok(systems.includes('auth.user'));
    assert.ok(systems.some(key => key.endsWith('.activitylog')));
    assert.equal(await toggle.isChecked(), false);
    const visible = await root.locator('[data-table-model]').evaluateAll(nodes => nodes.map(node => node.dataset.tableModel));
    assert.deepEqual(visible, catalog.filter(entry => !entry.is_system).map(entry => entry.key));
    await toggle.check();
    assert.equal(await model.isVisible(), true);
    assert.equal(await hidden.inputValue(), before);
    await toggle.uncheck();
    assert.equal(await model.count(), 0);
    assert.equal(await hidden.inputValue(), before);
    await page.locator('#universalDynamicModal .modal-header .btn-close').click();
    await page.waitForSelector('#universalDynamicModal.show', {state:'hidden'});
    model = await openTables(page);
    await model.locator('[data-column-toggle][data-column-name="email"]').click();
    const edited = await hidden.inputValue();
    await root.locator('[data-table-columns-system-toggle]').uncheck();
    assert.equal(await hidden.inputValue(), edited);
    await root.locator('[data-table-columns-system-toggle]').check();
    assert.equal(await model.locator('[data-column-toggle][data-column-name="email"]').getAttribute('aria-checked'), 'false');
    await model.locator('[data-table-columns-reset]').click();
    await save(page);
    await openTables(page, {showSystem:false});
    assert.equal(await root.locator('[data-table-columns-system-toggle]').isChecked(), false);
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

function headers(model) {
  return model.locator('[data-column-header]').evaluateAll(nodes => nodes.map(node => node.dataset.columnHeader));
}

async function save(page) {
  const [response] = await Promise.all([
    page.waitForResponse(response => response.request().method() === 'POST' && response.url().includes('/sys/modals/')),
    page.locator('#universalDynamicModalFooter button[type="submit"]').click(),
  ]);
  assert.equal(response.status(), 200);
  await page.waitForSelector('#universalDynamicModal.show', {state: 'hidden'});
}

test('chips, drag and reopening update the real users table', async () => {
  const {ctx, page, errors} = await loggedInPage(browser);
  try {
    let model = await openTables(page);
    const hidden = page.locator('#universalDynamicModal [name="tables_config"]');
    const original = await hidden.inputValue();
    await page.locator('#universalDynamicModal .modal-header .btn-close').click();
    await page.waitForSelector('#universalDynamicModal.show', {state: 'hidden'});
    model = await openTables(page);
    assert.equal(await hidden.inputValue(), original, 'opening must not rewrite JSON');
    const baseline = await headers(model);
    await model.locator('[data-column-toggle][data-column-name="email"]').click();
    assert.equal((await headers(model)).includes('email'), false);
    await model.locator('[data-column-header="full_name"]').dragTo(model.locator('[data-column-header]').first());
    assert.equal((await headers(model))[0], 'full_name');
    const expected = await headers(model);
    await save(page);
    await page.goto(`${BASE}/sys/users/`, {waitUntil: 'networkidle'});
    const actual = await page.locator('.dlux-data-table thead th').evaluateAll(nodes => nodes.map(node => node.dataset.dluxTableCol));
    assert.deepEqual(actual.filter(name => expected.includes(name)), expected);
    assert.equal(actual.includes('email'), false);
    model = await openTables(page);
    assert.deepEqual(await headers(model), expected);
    await model.locator('[data-column-toggle][data-column-name="email"]').click();
    assert.equal((await headers(model)).at(-1), 'email', 're-enabled columns append to the header strip');
    await model.locator('[data-table-columns-reset]').click();
    assert.deepEqual(await headers(model), baseline);
    await save(page);
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

test('keyboard order, sparse preservation, imported changes and last-column guard', async () => {
  const {ctx, page, errors} = await loggedInPage(browser);
  try {
    const model = await openTables(page);
    const baseline = await headers(model);
    const hidden = page.locator('#universalDynamicModal [name="tables_config"]');
    await hidden.evaluate(field => {
      const config = JSON.parse(field.value);
      config.columns = {
        'auth.user': {hidden: ['retired'], order: ['future_column']},
        'future.model': {hidden: ['other']},
      };
      field.value = JSON.stringify(config);
      field.dispatchEvent(new Event('change', {bubbles: true}));
    });
    const first = baseline[0];
    await model.locator(`[data-column-handle][data-column-name="${first}"]`).press('ArrowRight');
    assert.equal((await headers(model))[1], first);
    const value = JSON.parse(await hidden.inputValue());
    assert.deepEqual(value.columns['future.model'], {hidden: ['other']});
    assert.ok(value.columns['auth.user'].hidden.includes('retired'));
    assert.ok(value.columns['auth.user'].order.includes('future_column'));
    for (const name of baseline.slice(1)) {
      await model.locator(`[data-column-toggle][data-column-name="${name}"]`).click();
    }
    assert.deepEqual(await headers(model), [first]);
    assert.equal(await model.locator(`[data-column-toggle][data-column-name="${first}"]`).isDisabled(), true);
    await model.locator('[data-table-columns-reset]').click();
    const reset = JSON.parse(await hidden.inputValue());
    assert.equal(Object.hasOwn(reset.columns, 'auth.user'), false);
    assert.deepEqual(reset.columns['future.model'], {hidden: ['other']});
    assert.deepEqual(await headers(model), baseline);
    // Leave the shared harness fixture clean for following tests.
    await hidden.evaluate(field => {
      const config = JSON.parse(field.value);
      delete config.columns['future.model'];
      field.value = JSON.stringify(config);
      field.dispatchEvent(new Event('change', {bubbles:true}));
    });
    await save(page);
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

test('mobile tap controls reorder without overflowing the dialog', async () => {
  const {ctx, page, errors} = await loggedInPage(browser);
  try {
    await page.setViewportSize({width:390, height:844});
    const model = await openTables(page);
    const baseline = await headers(model);
    await model.locator('[data-column-header]').first().locator('[data-column-move="1"]').click();
    assert.equal((await headers(model))[1], baseline[0]);
    const geometry = await page.locator('#universalDynamicModal .modal-body').evaluate(node => ({width:node.clientWidth, scroll:node.scrollWidth}));
    assert.ok(geometry.scroll <= geometry.width + 2, JSON.stringify(geometry));
    await model.locator('[data-table-columns-reset]').click();
    await save(page);
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

test('discarding chip edits keeps the saved table unchanged', async () => {
  const {ctx, page, errors} = await loggedInPage(browser);
  try {
    let model = await openTables(page);
    await model.locator('[data-column-toggle][data-column-name="email"]').click();
    await page.keyboard.press('Escape');
    await page.waitForSelector('#dluxUnsavedModal.show');
    assert.equal(await model.isVisible(), true);
    await page.locator('[data-dlux-unsaved-discard]').click();
    await page.waitForSelector('#universalDynamicModal.show', {state:'hidden'});
    model = await openTables(page);
    assert.equal(await model.locator('[data-column-toggle][data-column-name="email"]').getAttribute('aria-checked'), 'true');
    await page.locator('#universalDynamicModal .modal-header .btn-close').click();
    await page.waitForSelector('#universalDynamicModal.show', {state:'hidden'});
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

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
    await setShown(page, model, 'email', false);
    const edited = await hidden.inputValue();
    await root.locator('[data-table-columns-system-toggle]').uncheck();
    assert.equal(await hidden.inputValue(), edited);
    await root.locator('[data-table-columns-system-toggle]').check();
    assert.equal(await model.locator('[data-column-header="email"]').getAttribute('data-column-enabled'), 'false');
    await resetTable(page, model);
    await save(page);
    await openTables(page, {showSystem:false});
    assert.equal(await root.locator('[data-table-columns-system-toggle]').isChecked(), false);
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

function headers(model) {
  return model.locator('[data-column-header][data-column-enabled="true"]').evaluateAll(nodes => nodes.map(node => node.dataset.columnHeader));
}

const inspector = page => page.locator('#universalDynamicModal [data-table-column-inspector]');
async function selectHeader(page, model, name) {
  await model.locator(`[data-column-handle][data-column-name="${name}"]`).click();
  await inspector(page).locator('[data-inspector-action="shown"]').waitFor({state:'visible'});
}
async function setShown(page, model, name, shown) {
  await selectHeader(page, model, name);
  await inspector(page).locator('[data-inspector-action="shown"] input').evaluate((input, value) => {
    input.checked = value;
    input.dispatchEvent(new Event('change', {bubbles:true}));
  }, shown);
  await inspector(page).locator('[data-inspector-action="clear-selection"]').click();
}
async function resetTable(page, model) {
  const clear = inspector(page).locator('[data-inspector-action="clear-selection"]');
  if (await clear.isVisible()) await clear.click();
  await model.locator('[data-table-select]').click();
  const reset = inspector(page).locator('[data-inspector-action="reset-table"]');
  await reset.waitFor({state:'visible'});
  assert.equal(await reset.locator('.bi-arrow-counterclockwise').count(), 1);
  await reset.click();
  await inspector(page).locator('[data-inspector-action="clear-selection"]').click();
  assert.equal(await model.locator('[data-table-select]').evaluate(node => node === document.activeElement), true);
}

async function save(page) {
  const [response] = await Promise.all([
    page.waitForResponse(response => response.request().method() === 'POST' && response.url().includes('/sys/modals/')),
    page.locator('#universalDynamicModalFooter button[type="submit"]').click(),
  ]);
  assert.equal(response.status(), 200);
  await page.waitForSelector('#universalDynamicModal.show', {state: 'hidden'});
}

test('inspector visibility, drag and reopening update the real users table', async () => {
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
    await setShown(page, model, 'email', false);
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
    const restoredOrder = await model.locator('[data-column-header]').evaluateAll(nodes => nodes.map(node => node.dataset.columnHeader));
    await setShown(page, model, 'email', true);
    assert.deepEqual(await headers(model), restoredOrder, 're-enabled columns retain their original position');
    await resetTable(page, model);
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
      await setShown(page, model, name, false);
    }
    assert.deepEqual(await headers(model), [first]);
    await selectHeader(page, model, first);
    assert.equal(await inspector(page).locator('[data-inspector-action="shown"] input').isDisabled(), true);
    assert.equal(await inspector(page).locator('[data-inspector-action="remove-column"]').isDisabled(), true);
    await resetTable(page, model);
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
    await resetTable(page, model);
    await save(page);
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

test('discarding inspector edits keeps the saved table unchanged', async () => {
  const {ctx, page, errors} = await loggedInPage(browser);
  try {
    let model = await openTables(page);
    await setShown(page, model, 'email', false);
    await page.keyboard.press('Escape');
    await page.waitForSelector('#dluxUnsavedModal.show');
    assert.equal(await model.isVisible(), true);
    await page.locator('[data-dlux-unsaved-discard]').click();
    await page.waitForSelector('#universalDynamicModal.show', {state:'hidden'});
    model = await openTables(page);
    assert.equal(await model.locator('[data-column-header="email"]').getAttribute('data-column-enabled'), 'true');
    await page.locator('#universalDynamicModal .modal-header .btn-close').click();
    await page.waitForSelector('#universalDynamicModal.show', {state:'hidden'});
    assert.deepEqual(errors, []);
  } finally { await ctx.close(); }
});

test('column inspector persists localized text, icons, two sorts and independent resets', async () => {
  const {ctx, page, errors} = await loggedInPage(browser);
  try {
    let model = await openTables(page);
    assert.equal(await model.locator('[data-column-toggle]').count(), 0);
    await selectHeader(page, model, 'email');
    await inspector(page).locator('[data-inspector-field="labels-en"] input').fill('Contact email');
    await inspector(page).locator('[data-inspector-field="labels-ar"] input').fill('البريد المخصص');
    await inspector(page).locator('[data-icon-toggle]').click();
    await inspector(page).locator('[data-icon-search]').fill('bi-envelope');
    await inspector(page).locator('[data-icon-suggestions] button[title="bi-envelope"]').click();
    await inspector(page).locator('[data-inspector-field="sort-priority"] select').selectOption('0');
    await inspector(page).locator('[data-inspector-field="sort-direction"] select').selectOption('desc');
    await selectHeader(page, model, 'username');
    await inspector(page).locator('[data-inspector-field="sort-priority"] select').selectOption('1');
    const config = JSON.parse(await page.locator('#universalDynamicModal [name="tables_config"]').inputValue());
    assert.deepEqual(config.columns['auth.user'].sorting, ['-email','username']);
    assert.deepEqual(config.columns['auth.user'].headers.email.labels, {en:'Contact email',ar:'البريد المخصص'});
    await inspector(page).locator('[data-inspector-action="clear-selection"]').click();
    await save(page);
    await page.goto(`${BASE}/sys/users/`,{waitUntil:'networkidle'});
    const email = page.locator('.dlux-data-table th[data-dlux-table-col="email"]');
    const expectedLabel = await page.locator('html').getAttribute('lang') === 'ar' ? 'البريد المخصص' : 'Contact email';
    assert.ok((await email.textContent()).includes(expectedLabel));
    assert.equal(await email.locator('.bi-envelope').count(),1);
    assert.equal(await email.locator('.is-ordered.is-desc').count(),1);
    assert.equal(await page.locator('.dlux-data-table th[data-dlux-table-col="username"] .is-ordered').count(),1);
    model = await openTables(page);
    await selectHeader(page, model, 'email');
    assert.equal(await inspector(page).locator('[data-inspector-field="labels-ar"] input').inputValue(),'البريد المخصص');
    await inspector(page).locator('[data-inspector-action="remove-column"]').click();
    assert.equal(await model.locator('[data-column-header="email"]').getAttribute('data-column-enabled'),'false');
    const reset = inspector(page).locator('[data-inspector-action="reset-column"]');
    assert.equal(await reset.locator('.bi-arrow-counterclockwise').count(),1);
    await reset.click();
    assert.equal(await model.locator('[data-column-header="email"]').getAttribute('data-column-enabled'),'true');
    const restored = JSON.parse(await page.locator('#universalDynamicModal [name="tables_config"]').inputValue());
    assert.equal(restored.columns['auth.user'].headers?.email,undefined);
    assert.deepEqual(restored.columns['auth.user'].sorting,['username']);
    await resetTable(page,model);
    await save(page);
    assert.deepEqual(errors,[]);
  } finally { await ctx.close(); }
});

test('Restore follows pending column overrides and reverted edits close cleanly', async () => {
  const {ctx,page,errors}=await loggedInPage(browser);
  try {
    const model=await openTables(page);
    const hidden=page.locator('#universalDynamicModal [name="tables_config"]');
    const original=await hidden.inputValue();
    await selectHeader(page,model,'email');
    const restore=inspector(page).locator('[data-inspector-action="reset-column"]');
    assert.equal((await restore.innerText()).trim(),'Restore');
    assert.equal(await restore.isDisabled(),true);
    const label=inspector(page).locator('[data-inspector-field="labels-en"] input');
    await label.fill('Temporary header');
    assert.equal(await restore.isEnabled(),true);
    await label.fill('');
    assert.equal(await restore.isDisabled(),true);
    assert.equal(await hidden.inputValue(),original);
    await label.fill('Temporary again');
    await restore.click();
    assert.equal(await restore.isDisabled(),true);
    await inspector(page).locator('[data-inspector-action="clear-selection"]').click();
    await setShown(page,model,'email',false);
    await setShown(page,model,'email',true);
    assert.equal(await hidden.inputValue(),original);
    await model.locator('[data-column-handle][data-column-name="username"]').press('ArrowRight');
    await model.locator('[data-column-handle][data-column-name="username"]').press('ArrowLeft');
    assert.equal(await hidden.inputValue(),original);
    await page.locator('#universalDynamicModal .modal-header .btn-close').click();
    await page.waitForSelector('#universalDynamicModal.show',{state:'hidden'});
    assert.equal(await page.locator('#dluxUnsavedModal.show').count(),0);
    let savedModel=await openTables(page);
    await selectHeader(page,savedModel,'email');
    await inspector(page).locator('[data-inspector-field="labels-en"] input').fill('Saved header');
    await inspector(page).locator('[data-inspector-action="clear-selection"]').click();
    await save(page);
    savedModel=await openTables(page);
    const saved=await hidden.inputValue();
    await selectHeader(page,savedModel,'email');
    const savedLabel=inspector(page).locator('[data-inspector-field="labels-en"] input');
    await savedLabel.fill('Changed saved header');
    await savedLabel.fill('Saved header');
    assert.equal(await hidden.inputValue(),saved);
    assert.equal(await inspector(page).locator('[data-inspector-action="reset-column"]').isEnabled(),true);
    await inspector(page).locator('[data-inspector-action="clear-selection"]').click();
    await page.locator('#universalDynamicModal .modal-header .btn-close').click();
    await page.waitForSelector('#universalDynamicModal.show',{state:'hidden'});
    assert.equal(await page.locator('#dluxUnsavedModal.show').count(),0);
    savedModel=await openTables(page);
    await resetTable(page,savedModel);
    await save(page);
    assert.deepEqual(errors,[]);
  } finally { await ctx.close(); }
});

test('ribbon buttons drag, save and reopen in their configured order', async () => {
  const {ctx,page,errors}=await loggedInPage(browser);
  try {
    async function openRibbon() {
      await page.goto(`${BASE}/sys/options/`,{waitUntil:'networkidle'});
      await page.locator('[data-dlux-settings-step="ribbon"]').click();
      const root=page.locator('#universalDynamicModal [data-ribbon-builder]');
      await root.locator('[data-ribbon-system-toggle]').check();
      return root;
    }
    const root=await openRibbon();
    const catalog=await root.evaluate(node=>JSON.parse(node.dataset.catalog));
    const host=catalog.find(entry=>entry.url && entry.actions.filter(action=>action.key).length>=2);
    assert.ok(host,'a real ribbon host supplies at least two destination buttons');
    const model=()=>page.locator('#universalDynamicModal [data-model]').filter({has:page.locator('[data-model-key]',{hasText:host.route_name})}).first();
    const buttons=()=>model().locator('[data-action-key]');
    const original=await buttons().evaluateAll(nodes=>nodes.map(node=>node.dataset.actionKey));
    await buttons().nth(1).dragTo(buttons().nth(0));
    const ordered=[original[1],original[0],...original.slice(2)];
    assert.deepEqual(await buttons().evaluateAll(nodes=>nodes.map(node=>node.dataset.actionKey)),ordered);
    await save(page);
    await page.goto(new URL(host.url,BASE).href,{waitUntil:'networkidle'});
    const actual=await page.locator('.dlux-ribbon-actions').first().evaluate(node=>[...node.querySelectorAll('a,button')].map(button=>{
      const endpoint=button.getAttribute('data-dynamic-modal')||button.getAttribute('formaction')||button.getAttribute('data-url')||button.getAttribute('data-start-url')||button.getAttribute('href');
      return endpoint?'dest:'+endpoint:'';
    }));
    assert.deepEqual(actual.filter(key=>ordered.includes(key)),ordered);
    await openRibbon();
    assert.deepEqual(await buttons().evaluateAll(nodes=>nodes.map(node=>node.dataset.actionKey)),ordered);
    await buttons().nth(1).dragTo(buttons().nth(0));
    assert.deepEqual(await buttons().evaluateAll(nodes=>nodes.map(node=>node.dataset.actionKey)),original);
    await save(page);
    assert.deepEqual(errors,[]);
  } finally { await ctx.close(); }
});

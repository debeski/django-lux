import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { chromium } from 'playwright';

const source = readFileSync(new URL('../dlux/static/dlux/helpers/dynamic_modal/js/entry_clipboard.js', import.meta.url), 'utf8');
const sticky = readFileSync(new URL('../dlux/static/dlux/helpers/sticky/js/main.js', import.meta.url), 'utf8');
const css = readFileSync(new URL('../dlux/static/dlux/helpers/dynamic_modal/css/entry_clipboard.css', import.meta.url), 'utf8');
const baseCss = readFileSync(new URL('../dlux/static/dlux/base/css/main.css', import.meta.url), 'utf8');
const bootstrapCss = readFileSync(new URL('../dlux/static/bootstrap/bootstrap.min.css', import.meta.url), 'utf8');
const html = `<html><head><meta name="viewport" content="width=device-width"><link rel="stylesheet" href="/clipboard.css"></head><body><form action="/entries/" data-app-label="catalog" data-model-name="product">
<label>Name<input name="name" ></label>
<label>Department<select name="department"><option value="a">A</option><option value="b">B</option></select></label>
<input name="password" type="password" >
<input name="secret" ><input name="id" type="hidden" >
<input name="excluded" data-dlux-entry-clipboard="false"><fieldset data-dlux-entry-clipboard="false"><input name="nested"></fieldset><textarea name="notes"></textarea></form>
<form class="dlux-ribbon" data-dlux-ribbon-autosubmit="true"><input name="ribbon_search" type="search"></form>
<form data-dlux-ribbon-autosubmit="true"><input name="ribbon_attribute_only"></form>
<div class="dlux-ribbon"><form><textarea name="ribbon_nested"></textarea></form></div>
<div class="dlux-reports-page"><form><input name="custom_start" type="text"></form></div>
<form class="dlux-report-builder"><input name="report_end" type="date"></form>
<div class="dlux-user-report" data-dlux-user-report><form><input name="report_query" type="search"></form></div>
<script src="/sticky.js"></script><script src="/clipboard.js" data-user="7" data-title="Entry clipboard" data-field="Target field" data-copy="Save snippet" data-clear="Clear clipboard"></script></body></html>`;

test('entry clipboard: default snippets, explicit opt-out, safe fields, isolation and responsive layout', async () => {
    const browser = await chromium.launch();
    const context = await browser.newContext();
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await context.route('http://clipboard.test/**', route => route.fulfill({
        contentType: route.request().url().endsWith('.css') ? 'text/css' : route.request().url().endsWith('.js') ? 'application/javascript' : 'text/html',
        body: route.request().url().endsWith('.css') ? bootstrapCss + baseCss + css : route.request().url().endsWith('/sticky.js') ? sticky : route.request().url().endsWith('.js') ? source : html,
    }));
    try {
        await page.goto('http://clipboard.test/entries/');
        assert.equal(await page.locator('.dlux-entry-clipboard-popover select option').count(), 2);
        assert.equal(await page.locator('.dlux-entry-clipboard-trigger').count(), 1);
        assert.equal(await page.locator('.dlux-ribbon .dlux-entry-clipboard-trigger, [data-dlux-ribbon-autosubmit] .dlux-entry-clipboard-trigger').count(), 0);
        assert.equal(await page.locator('.dlux-entry-clipboard-trigger').textContent(), '');
        assert.equal(await page.getByRole('button', { name: 'Close', exact: true }).count(), 0);
        assert.equal(await page.getByRole('button', { name: 'Save snippet', includeHidden: true }).textContent(), '');
        assert.equal(await page.getByRole('button', { name: 'Clear clipboard', includeHidden: true }).textContent(), '');
        assert.equal(await page.locator('.dlux-entry-clipboard-trigger .bi-clipboard[aria-hidden="true"]').count(), 1);
        await page.locator('[name=name]').fill('<b>Sample</b>');
        await page.getByRole('button', { name: 'Entry clipboard', exact: true }).click();
        await page.getByRole('button', { name: 'Save snippet' }).click();
        await page.locator('[name=name]').fill('');
        await page.getByRole('button', { name: 'Entry clipboard', exact: true }).click();
        await page.locator('.dlux-clipboard-row').filter({ hasText: '<b>Sample</b>' }).getByRole('button', { name: 'Replace field', exact: true }).click();
        assert.equal(await page.locator('[name=name]').inputValue(), '<b>Sample</b>');
        assert.equal(await page.locator('.dlux-entry-clipboard-popover b').count(), 0);
        await page.locator('[name=name]').fill('prefix selected suffix');
        await page.locator('[name=name]').evaluate(field => field.setSelectionRange(7, 15));
        await page.getByRole('button', { name: 'Entry clipboard', exact: true }).click();
        await page.getByRole('button', { name: 'Save snippet' }).click();
        await page.locator('.dlux-clipboard-row').filter({ hasText: 'selected' }).getByRole('button', { name: 'Add to field', exact: true }).click();
        assert.equal(await page.locator('[name=name]').inputValue(), 'prefix selectedselected suffix');
        await page.getByRole('button', { name: 'selected', exact: true }).click();
        assert.equal(await page.locator('.dlux-clipboard-content').textContent(), 'selected');
        await page.getByRole('button', { name: 'Back to snippets' }).click();
        assert.equal(await page.locator('.dlux-clipboard-list').isVisible(), true);
        await page.getByRole('button', { name: 'Entry clipboard', exact: true }).click();
        await page.getByRole('searchbox', { name: 'Find a snippet' }).fill('sample');
        assert.equal(await page.getByRole('button', { name: 'selected', exact: true }).count(), 0);
        await page.keyboard.press('Escape');
        await page.waitForFunction(() => document.querySelector('.dlux-entry-clipboard-trigger').getAttribute('aria-expanded') === 'false');
        assert.equal(await page.getByRole('button', { name: 'Entry clipboard', exact: true }).getAttribute('aria-expanded'), 'false');
        await page.reload();
        assert.equal(await page.locator('[name=name]').inputValue(), '');
        assert.equal(await page.locator('input[type=checkbox]').count(), 1);
        assert.equal(await page.locator('[data-dlux-assist-bar]').count(), 1);
        assert.equal(await page.locator('[data-dlux-assist-bar] .dlux-entry-clipboard-trigger').count(), 1);
        assert.equal(await page.evaluate(() => 'capture' in DluxEntryClipboard), false);
        await page.locator('[name=name]').focus();
        await page.keyboard.press('Alt+Shift+KeyC');
        assert.equal(await page.locator('[popover]').evaluate(node => node.matches(':popover-open')), true);
        for (const width of [390, 1280]) {
            await page.setViewportSize({ width, height: 800 });
            await page.waitForFunction(() => { const box = document.querySelector('[popover]').getBoundingClientRect(); return box.left >= 0 && box.right <= innerWidth && box.bottom <= innerHeight; });
            assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
            assert.equal(await page.locator('[popover]').evaluate(node => { const box = node.getBoundingClientRect(); return box.left >= 0 && box.right <= innerWidth && box.bottom <= innerHeight; }), true);
        }
        await page.locator('html').evaluate(node => node.dir = 'rtl');
        assert.equal(await page.locator('.dlux-clipboard-row').evaluateAll(nodes => nodes.every(node => node.scrollWidth <= node.clientWidth)), true);
        await page.mouse.click(30, 700);
        await page.waitForFunction(() => !document.querySelector('[popover]').matches(':popover-open'));
        await page.getByRole('button', { name: 'Entry clipboard', exact: true }).click();
        const other = await context.newPage();
        await other.goto('http://clipboard.test/entries/');
        assert.equal(await other.getByRole('button', { name: '<b>Sample</b>' }).count(), 0);
        await page.getByRole('button', { name: 'Clear clipboard' }).click();
        assert.equal(await page.getByRole('button', { name: '<b>Sample</b>' }).count(), 0);
        assert.deepEqual(errors, []);
    } finally { await browser.close(); }
});

test('modal snippets share the sticky header and Save & Add More preserves the clicked action', async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    const modal = readFileSync(new URL('../dlux/static/dlux/helpers/dynamic_modal/js/main.js', import.meta.url), 'utf8');
    const bootstrap = readFileSync(new URL('../dlux/static/bootstrap/bootstrap.bundle.min.js', import.meta.url), 'utf8');
    const form = '<form action="/entries/" data-app-label="catalog" data-model-name="product"><label>Name<input name="name"></label><button type="submit" name="save_add_more" value="1">Save & Add More</button></form>';
    const shell = html.replace(/<form[\s\S]*?<\/form>/, '<div id="universalDynamicModal" class="modal"><div class="modal-dialog"><div class="modal-content"><span id="dynamicModalTitleText"></span><div id="universalDynamicModalBody"></div><div id="universalDynamicModalFooter"></div></div></div></div>')
        .replace('</body>', '<script src="/bootstrap.js"></script><script src="/modal.js"></script></body>');
    let submitted = false;
    await page.route('http://clipboard.test/**', async route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/entries/') {
            if (request.method() === 'POST') {
                submitted = /name="save_add_more"/.test(request.postData());
                await route.fulfill({ json: { success: true, add_more: true } });
            } else await route.fulfill({ json: { html: form } });
        } else await route.fulfill({
            contentType: path.endsWith('.css') ? 'text/css' : path.endsWith('.js') ? 'application/javascript' : 'text/html',
            body: path === '/clipboard.css' ? bootstrapCss + baseCss + css : path === '/clipboard.js' ? source : path === '/sticky.js' ? sticky : path === '/bootstrap.js' ? bootstrap : path === '/modal.js' ? modal : shell,
        });
    });
    try {
        await page.goto('http://clipboard.test/');
        await page.evaluate(() => document.dispatchEvent(new CustomEvent('dlux:dynamic_modal:open', { detail: { data: { url: '/entries/' } } })));
        await page.locator('[name=name]').fill('Sample');
        assert.equal(await page.locator('[data-dlux-assist-bar]').count(), 1);
        assert.equal(await page.locator('[data-dlux-assist-bar] .dlux-entry-clipboard-trigger').count(), 1);
        await page.getByRole('button', { name: 'Entry clipboard', exact: true }).click();
        await page.getByRole('button', { name: 'Save snippet' }).click();
        await page.keyboard.press('Escape');
        await Promise.all([page.waitForEvent('domcontentloaded'), page.getByRole('button', { name: 'Save & Add More' }).click()]);
        await page.locator('[name=name]').waitFor();
        assert.equal(submitted, true);
        assert.equal(await page.locator('[name=name]').inputValue(), '');
        await page.getByRole('button', { name: 'Entry clipboard', exact: true }).click();
        await page.locator('.dlux-clipboard-row').filter({ hasText: 'Sample' }).getByRole('button', { name: 'Replace field', exact: true }).click();
        assert.equal(await page.locator('[name=name]').inputValue(), 'Sample');
    } finally { await browser.close(); }
});

test('custom full-page forms show the assisted-entry legend without claiming sticky capability', async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    const custom = html.replace('data-app-label="catalog" data-model-name="product"', '');
    await page.route('http://clipboard.test/**', route => route.fulfill({
        contentType: route.request().url().endsWith('.js') ? 'application/javascript' : 'text/html',
        body: route.request().url().endsWith('/sticky.js') ? sticky : route.request().url().endsWith('/clipboard.js') ? source : custom,
    }));
    try {
        await page.goto('http://clipboard.test/custom/');
        assert.equal(await page.locator('[data-dlux-assist-bar]').count(), 1);
        assert.equal(await page.locator('.dlux-assist-bar__legend').textContent(), ' Assisted entry');
        assert.equal(await page.locator('[data-dlux-assist-bar] .dlux-entry-clipboard-trigger').count(), 1);
        assert.equal(await page.locator('[data-dlux-assist-pref="sticky_forms"]').count(), 0);
    } finally { await browser.close(); }
});

test('clipboard snippets are purged on logout/account switch and stale restored pages reload', async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    const baseHead = readFileSync(new URL('../dlux/static/dlux/base/js/base_head.js', import.meta.url), 'utf8');
    let user = '7';
    await page.route('http://clipboard.test/**', route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/identity.js') return route.fulfill({ contentType: 'application/javascript', body: baseHead });
        if (path === '/clipboard.js') return route.fulfill({ contentType: 'application/javascript', body: source });
        if (path === '/sticky.js') return route.fulfill({ contentType: 'application/javascript', body: sticky });
        let body = html.replace('<head>', `<head><script src="/identity.js" data-clipboard-user="${user}"></script>`)
            .replace('data-user="7"', `data-user="${user}"`);
        if (!user && path !== '/missing-owner/') body = body.replace(/<script src="\/clipboard.js"[^>]*><\/script>/, '');
        return route.fulfill({ contentType: 'text/html', body });
    });
    const copy = async text => {
        await page.locator('[name=name]').fill(text);
        await page.getByRole('button', { name: 'Entry clipboard', exact: true }).click();
        await page.getByRole('button', { name: 'Save snippet' }).click();
    };
    try {
        await page.goto('http://clipboard.test/account/');
        await copy('User A private snippet');
        assert.equal(await page.evaluate(() => JSON.parse(sessionStorage.getItem('dlux:entry-clipboard:7')).snippets[0]), 'User A private snippet');
        user = '8';
        await page.reload();
        assert.equal(await page.getByRole('button', { name: 'User A private snippet' }).count(), 0);
        assert.equal(await page.evaluate(() => sessionStorage.getItem('dlux:entry-clipboard:7')), null);
        await copy('User B private snippet');
        user = '';
        await page.reload();
        assert.equal(await page.locator('.dlux-entry-clipboard-trigger').count(), 0);
        assert.equal(await page.evaluate(() => Object.keys(sessionStorage).some(key => key.startsWith('dlux:entry-clipboard:'))), false);
        await page.goto('http://clipboard.test/missing-owner/');
        assert.equal(await page.locator('.dlux-entry-clipboard-trigger').count(), 0);
        assert.equal(await page.evaluate(() => typeof window.DluxEntryClipboard), 'undefined');
        user = '7';
        await page.reload();
        assert.equal(await page.locator('.dlux-clipboard-row').count(), 0);
        await copy('Stale page snippet');
        user = '8';
        await Promise.all([
            page.waitForEvent('domcontentloaded'),
            page.evaluate(() => {
                sessionStorage.setItem('dlux:entry-clipboard-owner', '8');
                window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true }));
            }),
        ]);
        assert.equal(await page.locator('.dlux-clipboard-row').count(), 0);
        assert.equal(await page.evaluate(() => sessionStorage.getItem('dlux:entry-clipboard:7')), null);
        assert.equal(await page.evaluate(() => sessionStorage.getItem('dlux:entry-clipboard-owner')), '8');
    } finally { await browser.close(); }
});

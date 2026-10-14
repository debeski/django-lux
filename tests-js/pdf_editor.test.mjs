import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../dlux/static/dlux/pdf/js/editor.js', import.meta.url), 'utf8');
const tick = () => new Promise(resolve => setImmediate(resolve));

function deferred() {
    let resolve;
    const promise = new Promise(done => { resolve = done; });
    return { promise, resolve };
}

function element() {
    return {
        listeners: {}, dataset: {}, children: [], disabled: false,
        classList: { add() {}, remove() {}, toggle() {} }, style: {},
        setAttribute() {},
        getBoundingClientRect() { return { left: 0, width: 100 }; },
        closest() { return null; },
        addEventListener(name, fn) { this.listeners[name] = fn; },
        removeEventListener(name) { delete this.listeners[name]; },
        appendChild(child) { this.children.push(child); },
        getContext() { return {}; },
    };
}

function harness(currentUrl = '') {
    const selectors = {};
    for (const name of ['[data-editor-status]', '[data-page-grid]', '#dlux-pdf-file-input', '[data-add-files]', '[data-save-pdf]', '[name=csrfmiddlewaretoken]']) selectors[name] = element();
    selectors['#dlux-pdf-file-input'].files = [];
    const modal = element();
    const shell = {
        dataset: { currentUrl, saveUrl: '/save/', modalMode: '1', revision: 'r1' },
        isConnected: true,
        querySelector: name => selectors[name] || null,
        closest: () => modal,
    };
    const tasks = [];
    let reloads = 0;
    let requests = 0;
    const reply = deferred();
    const forms = [];
    const window = {
        location: { reload() { reloads += 1; } },
        getComputedStyle: () => ({ direction: 'ltr' }),
        pdfjsLib: {
            GlobalWorkerOptions: {},
            getDocument() {
                const wait = deferred();
                const task = { ...wait, destroyed: 0, async destroy() { this.destroyed += 1; } };
                tasks.push(task);
                return task;
            },
        },
    };
    vm.runInNewContext(source, {
        window,
        document: {
            readyState: 'complete', documentElement: {},
            querySelectorAll: () => [shell], createElement: element,
        },
        MutationObserver: class { observe() {} },
        FormData: class { append(name, value) { forms.push([name, value]); } },
        setTimeout, clearTimeout,
        fetch() { requests += 1; return reply.promise; },
    });
    const pdf = { numPages: 1, async getPage() {
        return { getViewport: () => ({ width: 100, height: 200 }), render: () => ({ promise: Promise.resolve() }) };
    } };
    async function upload() {
        selectors['#dlux-pdf-file-input'].files = [{ name: 'new.pdf', async arrayBuffer() { return new ArrayBuffer(1); } }];
        const done = selectors['#dlux-pdf-file-input'].listeners.change();
        await tick();
        tasks.at(-1).resolve(pdf);
        await done;
    }
    async function choose(name) {
        selectors['#dlux-pdf-file-input'].files = [{ name, async arrayBuffer() { return new ArrayBuffer(1); } }];
        await selectors['#dlux-pdf-file-input'].listeners.change();
    }
    return { shell, selectors, tasks, pdf, upload, choose, reply, forms, reloads: () => reloads, requests: () => requests };
}

test('save waits for current PDF even after uploaded pages become ready', async () => {
    const h = harness('/current/');
    await h.upload();
    assert.equal(h.selectors['[data-save-pdf]'].disabled, true);
    await h.selectors['[data-save-pdf]'].listeners.click();
    assert.equal(h.requests(), 0);
    h.tasks[0].resolve(h.pdf);
    await tick();
    assert.equal(h.selectors['[data-save-pdf]'].disabled, false);
});

test('disposing an editor cancels its in-flight load', async () => {
    const h = harness('/current/');
    h.shell.disposePdfEditor();
    assert.equal(h.tasks[0].destroyed, 1);
    h.tasks[0].resolve(h.pdf);
    await tick();
    assert.equal(h.selectors['[data-page-grid]'].children.length, 0);
});

test('a late successful save cannot reload after editor replacement', async () => {
    const h = harness();
    await h.upload();
    const saving = h.selectors['[data-save-pdf]'].listeners.click();
    h.shell.disposePdfEditor();
    h.shell.isConnected = false;
    h.reply.resolve({ ok: true, async text() { return '{"success":true}'; } });
    await saving;
    assert.equal(h.reloads(), 0);
});

test('page rotation and fit travel in the save manifest', async () => {
    const h = harness();
    await h.upload();
    const card = () => h.selectors['[data-page-grid]'].children.at(-1);
    const footer = () => card().children[1];
    footer().children[2].listeners.click();
    footer().children[2].listeners.click();
    h.selectors['[data-save-pdf]'].listeners.click();
    await tick();
    const manifest = JSON.parse(h.forms.find(([name]) => name === 'manifest')[1]);
    assert.deepEqual(manifest, [{ source: 'upload_0', page: 1, rotate: 180 }]);
});

test('files outside the accepted kinds are refused without a request', async () => {
    const h = harness();
    await h.choose('photo.png');
    assert.equal(h.requests(), 0);
    assert.equal(h.tasks.length, 0);
    assert.match(h.selectors['[data-editor-status]'].textContent, /cannot be added/);
});

test('a page can be dragged to the last position', async () => {
    const h = harness();
    h.pdf.numPages = 3;
    await h.upload();
    const grid = h.selectors['[data-page-grid]'];
    // The fake grid never empties on re-render; the current cards are the last three.
    const cards = () => grid.children.slice(-3);
    const order = () => cards().map(card => card.children[1].children[1].textContent.slice(-1));
    const drop = (card, clientX) => card.listeners.drop({ preventDefault() {}, stopPropagation() {}, clientX });

    cards()[0].listeners.dragstart();
    drop(cards()[2], 80);
    assert.deepEqual(order(), ['2', '3', '1']);

    cards()[0].listeners.dragstart();
    grid.listeners.drop({ preventDefault() {}, target: grid });
    assert.deepEqual(order(), ['3', '1', '2']);

    cards()[2].listeners.dragstart();
    drop(cards()[0], 20);
    assert.deepEqual(order(), ['2', '3', '1']);
});

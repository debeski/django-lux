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
        classList: { add() {}, remove() {} },
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
    const window = {
        location: { reload() { reloads += 1; } },
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
        FormData: class { append() {} },
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
    return { shell, selectors, tasks, pdf, upload, reply, reloads: () => reloads, requests: () => requests };
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

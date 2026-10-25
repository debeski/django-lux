import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';

const root = process.argv[2];
const standalone = process.argv[3];
const clientPath = path.join(root, 'dlux/static/dlux/helpers/scanlink/js/main.js');
const buttonPath = path.join(root, 'dlux/static/dlux/helpers/scanlink/js/scan_button.js');
const updatePath = path.join(root, 'dlux/static/dlux/system/js/scanlink_update.js');
let passed = 0;

function runtime(file, fetch, secure = true, extra = {}) {
    const window = { isSecureContext: secure, location: { protocol: 'https:' }, setTimeout, DLUX_STRINGS: {}, ...extra.window };
    const context = vm.createContext({ window, fetch, AbortController, setTimeout, clearTimeout, URLSearchParams, MutationObserver: class { observe() {} }, ...extra });
    vm.runInContext(fs.readFileSync(file, 'utf8'), context);
    return context;
}

const response = (value) => ({ ok: true, json: async () => value });
for (const file of [clientPath, standalone].filter(Boolean)) {
    const calls = [];
    let context = runtime(file, async (url) => {
        calls.push(url);
        if (url.startsWith('https:')) throw new TypeError('TLS not ready');
        return response({ status: 'ok', version: '0.7.4' });
    });
    let client = vm.runInContext('new ScanLink()', context);
    assert.equal((await client.checkHealth()).version, '0.7.4');
    assert.equal(calls.length, 2);
    assert.match(client.baseUrl, /^http:/);
    assert.equal(client.connectionError, null);
    passed++;

    context = runtime(file, async () => { throw new TypeError('failed'); }, false);
    client = vm.runInContext('new ScanLink()', context);
    assert.equal(await client.checkHealth(), null);
    assert.equal(client.connectionError.code, 'insecure_origin');
    passed++;

    context = runtime(file, async () => { throw new TypeError('failed'); });
    client = vm.runInContext('new ScanLink()', context);
    assert.equal(await client.checkHealth(), null);
    assert.equal(client.connectionError.code, 'helper_unavailable');
    assert.match(client.connectionError.message, /choose Allow/);
    passed++;

    context = runtime(file, async (url, options) => {
        if (url.startsWith('http:')) return response({ status: 'ok' });
        return { ok: true, json: () => new Promise((resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('timeout')))) };
    });
    client = vm.runInContext('new ScanLink({ healthTimeoutMs: 10 })', context);
    assert.equal((await client.checkHealth()).status, 'ok');
    assert.match(client.baseUrl, /^http:/);
    passed++;
}

{
    const error = Object.assign(new Error('internal failure'), { code: 'insecure_origin' });
    const document = { querySelectorAll: () => [], addEventListener() {} };
    const context = runtime(clientPath, async () => { throw new TypeError('failed'); }, false, { document });
    context.window.DLUX_STRINGS.scan_insecure_origin_message = 'افتح العنوان الآمن';
    vm.runInContext(fs.readFileSync(buttonPath, 'utf8'), context);
    const messages = context.window.DluxScan.messagesFor(null);
    assert.equal(context.window.DluxScan.errorMessage(messages, error), 'افتح العنوان الآمن');
    await assert.rejects(context.window.DluxScan.scan({ messages }), (err) => err.code === 'insecure_origin' && err.message === 'افتح العنوان الآمن');
    passed++;
}

async function updateScenario(secure, health, failed = false, latest = '0.7.5') {
    const calls = [];
    const nodes = new Map();
    for (const name of ['connection', 'local-version', 'latest-version', 'status', 'actions', 'notice']) {
        nodes.set(`[data-scanlink-${name}]`, { textContent: '', hidden: true, children: [], replaceChildren() { this.children = []; }, appendChild(node) { this.children.push(node); } });
    }
    const card = {
        dataset: { origins: JSON.stringify(['https://localhost:5443', 'http://localhost:5000']), manifestUrl: '/manifest' },
        querySelector: (selector) => nodes.get(selector), isConnected: true,
    };
    const document = {
        readyState: 'complete', querySelectorAll: () => [card],
        createElement: () => ({ setAttribute() {} }),
    };
    runtime(updatePath, async (url) => {
        calls.push(url);
        if (url === '/manifest') return response({ latest_version: latest, downloads: { x64: '/installer' } });
        if (failed || url.startsWith('https:')) throw new TypeError('not reachable');
        return response(health);
    }, secure, { document });
    await new Promise((resolve) => setTimeout(resolve, 20));
    return { calls, nodes };
}

let result = await updateScenario(true, { version: '0.7.5', https_setup: 'ready' });
assert.ok(result.calls.includes('http://localhost:5000/health'));
assert.equal(result.nodes.get('[data-scanlink-connection]').textContent, 'Connected');
assert.equal(result.nodes.get('[data-scanlink-notice]').hidden, true);
passed++;
result = await updateScenario(true, { version: '0.7.5', https_setup: 'failed' });
assert.match(result.nodes.get('[data-scanlink-notice]').textContent, /Retry secure connection setup/);
passed++;
result = await updateScenario(false, null, true);
assert.match(result.nodes.get('[data-scanlink-notice]').textContent, /secure address/);
assert.equal(result.nodes.get('[data-scanlink-actions]').children.length, 1);
passed++;
for (const [installed, latest, expected] of [
    ['0.7.5', '0.7.5b1', 'ScanLink is up to date.'],
    ['0.7.5b10', '0.7.5b2', 'ScanLink is up to date.'],
    ['0.7.5b1', '0.7.5b2', 'A newer ScanLink version is available.'],
    ['0.7.5rc1', '0.7.5', 'A newer ScanLink version is available.'],
]) {
    result = await updateScenario(true, { version: installed, https_setup: 'ready' }, false, latest);
    assert.equal(result.nodes.get('[data-scanlink-status]').textContent, expected);
    passed++;
}
console.log(JSON.stringify({ passed }));

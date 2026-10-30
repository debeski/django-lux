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

    const submitted = [];
    context = runtime(file, async (url, options) => {
        if (options.method === 'GET') return response({ status: 'ok' });
        submitted.push(url);
        throw new TypeError('accepted by server; response lost');
    });
    client = vm.runInContext('new ScanLink()', context);
    client.preferredUrl = 'https://localhost:5443';
    await assert.rejects(client.startScan(), (error) => error.code === 'scan_request_uncertain');
    assert.equal(submitted.length, 1);
    assert.equal(client.currentJobId, null);
    passed++;

    const negotiated = [];
    context = runtime(file, async (url, options) => {
        negotiated.push([url, options.method]);
        if (url.startsWith('https:')) throw new TypeError('TLS unavailable');
        return response(options.method === 'POST' ? { job_id: 'only-job', status: 'queued' } : { status: 'ok' });
    });
    client = vm.runInContext('new ScanLink()', context);
    assert.equal((await client.startScan()).job_id, 'only-job');
    assert.deepEqual(negotiated.map(x => x[1]), ['GET', 'GET', 'POST']);
    assert.match(negotiated[2][0], /^http:/);
    passed++;

    const blocked = [];
    context = runtime(file, async (url, options) => { blocked.push(options.method); throw new TypeError('offline'); });
    client = vm.runInContext('new ScanLink()', context);
    await assert.rejects(client.startScan(), (error) => error.code === 'helper_unavailable');
    assert.ok(blocked.every(method => method === 'GET'));
    passed++;

    let bodyPosts = 0;
    context = runtime(file, async (url, options) => {
        if (options.method === 'GET') return response({ status: 'ok' });
        bodyPosts++;
        return { ok: true, json: async () => { throw new TypeError('response body lost'); } };
    });
    client = vm.runInContext('new ScanLink()', context);
    await assert.rejects(client.startScan(), (error) => error.code === 'scan_request_uncertain');
    assert.equal(bodyPosts, 1);
    passed++;

    const restarted = [];
    let httpsUp = true;
    context = runtime(file, async (url, options) => {
        restarted.push([url, options.method]);
        if (url.startsWith('https:') && !httpsUp) throw new TypeError('HTTPS setup failed after restart');
        return response(options.method === 'POST' ? { job_id: 'restart-job', status: 'queued' } : { status: 'ok' });
    });
    client = vm.runInContext('new ScanLink()', context);
    await client.startScan();
    assert.match(client.baseUrl, /^https:/);
    httpsUp = false;
    restarted.length = 0;
    assert.equal((await client.startScan()).job_id, 'restart-job');
    assert.deepEqual(restarted.filter(([, method]) => method === 'POST').map(([url]) => url), ['http://localhost:5000/scan']);
    assert.match(client.baseUrl, /^http:/);
    passed++;

    for (const [secure, code] of [[true, 'helper_unavailable'], [false, 'insecure_origin']]) {
        const afterClose = [];
        let helperUp = true;
        context = runtime(file, async (url, options) => {
            if (helperUp) return response({ status: 'ok' });
            afterClose.push(options.method);
            throw new TypeError('ScanLink closed');
        }, secure);
        client = vm.runInContext('new ScanLink()', context);
        assert.ok(await client.checkHealth());
        helperUp = false;
        await assert.rejects(client.startScan(), (error) => error.code === code);
        assert.ok(afterClose.length > 0 && afterClose.every(method => method === 'GET'));
        passed++;
    }

    const healthyPosts = [];
    let dropPost = false;
    context = runtime(file, async (url, options) => {
        if (options.method === 'GET') return response({ status: 'ok' });
        healthyPosts.push(url);
        if (dropPost) throw new TypeError('accepted by server; response lost');
        return response({ job_id: 'first-job', status: 'queued' });
    });
    client = vm.runInContext('new ScanLink({ baseUrl: "http://localhost:5000" })', context);
    await client.startScan();
    healthyPosts.length = 0;
    dropPost = true;
    await assert.rejects(client.startScan(), (error) => error.code === 'scan_request_uncertain');
    assert.deepEqual(healthyPosts, ['http://localhost:5000/scan']);
    passed++;
}

{
    const error = Object.assign(new Error('internal failure'), { code: 'insecure_origin' });
    const document = { querySelectorAll: () => [], addEventListener() {} };
    const context = runtime(clientPath, async () => { throw new TypeError('failed'); }, false, { document });
    context.window.DLUX_STRINGS.scan_request_uncertain_message = 'تحقق من ScanLink قبل بدء مسح آخر';
    context.window.DLUX_STRINGS.scan_insecure_origin_message = 'افتح العنوان الآمن';
    vm.runInContext(fs.readFileSync(buttonPath, 'utf8'), context);
    const messages = context.window.DluxScan.messagesFor(null);
    assert.equal(context.window.DluxScan.errorMessage(messages, { code: 'scan_request_uncertain' }), 'تحقق من ScanLink قبل بدء مسح آخر');
    assert.equal(context.window.DluxScan.errorMessage(messages, error), 'افتح العنوان الآمن');
    await assert.rejects(context.window.DluxScan.scan({ messages }), (err) => err.code === 'insecure_origin' && err.message === 'افتح العنوان الآمن');
    passed++;
}

{
    const posts = [];
    let httpsUp = true;
    let helperUp = true;
    const document = { querySelectorAll: () => [], addEventListener() {} };
    const context = runtime(clientPath, async (url, options) => {
        if (!helperUp || (url.startsWith('https:') && !httpsUp)) throw new TypeError('not reachable');
        if (options.method === 'POST') {
            posts.push(url);
            return response({ job_id: 'dlux-job', status: 'queued' });
        }
        if (url.endsWith('/result')) return { ok: true, blob: async () => 'pdf' };
        if (url.includes('/scan/')) return response({ job_id: 'dlux-job', status: 'completed', page_count: 1 });
        return response({ status: 'ok', twain_available: true, busy: false });
    }, true, { document });
    vm.runInContext(fs.readFileSync(buttonPath, 'utf8'), context);
    const scan = () => context.window.DluxScan.scan({ messages: context.window.DluxScan.messagesFor(null) });
    assert.equal(await scan(), 'pdf');
    httpsUp = false;
    assert.equal(await scan(), 'pdf');
    assert.deepEqual(posts, ['https://localhost:5443/scan', 'http://localhost:5000/scan']);
    passed++;
    helperUp = false;
    await assert.rejects(scan(), (err) => err.code === 'helper_unavailable');
    assert.equal(posts.length, 2);
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

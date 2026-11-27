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
    const { window: windowExtra, ...globals } = extra;
    const window = { isSecureContext: secure, location: { protocol: 'https:' }, setTimeout, DLUX_STRINGS: {}, ...windowExtra };
    const context = vm.createContext({ window, fetch, AbortController, setTimeout, clearTimeout, URLSearchParams, Blob, console: { warn() {}, log() {}, error() {} }, MutationObserver: class { observe() {} }, ...globals });
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

    // A refused website learns why, so the page can link instead of saying ScanLink is not running.
    const refusal = { ok: false, status: 403, json: async () => ({ error: { code: 'origin_not_allowed', message: 'This website is not linked to ScanLink.' } }) };
    const linkBodies = [];
    let linkAnswer = response({ linked: true, prompted: true, sites: ['https://archive.example', 'https://crm.example'] });
    context = runtime(file, async (url, options) => {
        if (url.endsWith('/link')) {
            linkBodies.push([url, JSON.parse(options.body)]);
            return linkAnswer;
        }
        if (url.startsWith('http:')) throw new TypeError('HTTP not used');
        return refusal;
    });
    client = vm.runInContext('new ScanLink()', context);
    assert.equal(await client.checkHealth(true), null);
    assert.equal(client.connectionError.code, 'origin_not_allowed');
    assert.match(client.baseUrl, /^https:/);
    await assert.rejects(client.startScan(), (error) => error.code === 'origin_not_allowed');
    assert.equal((await client.link(['https://crm.example'])).prompted, true);
    assert.deepEqual(linkBodies, [['https://localhost:5443/link', { sites: ['https://crm.example'] }]]);
    linkAnswer = { ok: false, status: 403, json: async () => ({ error: { code: 'link_declined', message: 'declined' } }) };
    await assert.rejects(client.link([]), (error) => error.code === 'link_declined');
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
    // ScanLink's own error codes reach the operator translated, and the page waits
    // longer than ScanLink's 10-minute job deadline so ScanLink reports first.
    const document = { querySelectorAll: () => [], addEventListener() {} };
    const context = runtime(clientPath, async (url, options) => {
        if (options.method === 'POST') return response({ job_id: 'slow-job', status: 'queued' });
        return response({ status: 'ok', twain_available: true, busy: false });
    }, true, { document });
    Object.assign(context.window.DLUX_STRINGS, {
        scan_no_pages_message: 'لا صفحات', scan_acquire_failed_message: 'توقف الماسح',
        scan_worker_crashed_message: 'توقفت العملية', scan_origin_not_allowed_message: 'موقع غير مسموح',
        scan_timeout_message: 'استغرق طويلا',
    });
    vm.runInContext(fs.readFileSync(buttonPath, 'utf8'), context);
    const scan = context.window.DluxScan;
    const messages = scan.messagesFor(null);
    const expected = {
        no_pages_scanned: 'لا صفحات', acquire_failed: 'توقف الماسح', scan_worker_crashed: 'توقفت العملية',
        origin_not_allowed: 'موقع غير مسموح', payload_too_large: messages.failed, invalid_host: messages.failed,
    };
    for (const [code, text] of Object.entries(expected)) {
        assert.equal(scan.errorMessage(messages, { code, message: 'English from ScanLink' }), text, code);
    }
    messages.timeout = 'استغرق طويلا';
    assert.equal(scan.errorMessage(messages, { code: 'scan_idle_timeout', message: 'English' }), 'استغرق طويلا');
    let waited = null;
    context.window.ScanLink.prototype.waitForResult = async (jobId, options) => { waited = [jobId, options.timeoutMs]; return 'pdf'; };
    assert.equal(await scan.scan({ messages }), 'pdf');
    assert.deepEqual(waited, ['slow-job', 11 * 60 * 1000]);
    assert.ok(scan.waitMs > 615 * 1000, 'longer than ScanLink\'s job deadline');
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
        if (url.endsWith('/result')) return { ok: true, blob: async () => new Blob(['%PDF-1.4 scanned']) };
        if (url.includes('/scan/')) return response({ job_id: 'dlux-job', status: 'completed', page_count: 1 });
        return response({ status: 'ok', twain_available: true, busy: false });
    }, true, { document });
    vm.runInContext(fs.readFileSync(buttonPath, 'utf8'), context);
    const scan = () => context.window.DluxScan.scan({ messages: context.window.DluxScan.messagesFor(null) });
    const pdfText = async () => (await scan()).text();
    assert.equal(await pdfText(), '%PDF-1.4 scanned');
    httpsUp = false;
    assert.equal(await pdfText(), '%PDF-1.4 scanned');
    assert.deepEqual(posts, ['https://localhost:5443/scan', 'http://localhost:5000/scan']);
    passed++;
    helperUp = false;
    await assert.rejects(scan(), (err) => err.code === 'helper_unavailable');
    assert.equal(posts.length, 2);
    passed++;
}

function linkingPage(adminSites, state) {
    const document = {
        querySelectorAll: () => [], addEventListener() {},
        getElementById: (id) => (id === 'dlux-scanlink-sites' ? { textContent: JSON.stringify(adminSites) } : null),
    };
    const context = runtime(clientPath, async (url, options) => {
        state.calls.push(`${options.method} ${url.replace(/^https:\/\/localhost:5443/, '')}`);
        if (url.endsWith('/link')) {
            state.linkBodies.push(JSON.parse(options.body));
            if (state.declined) return { ok: false, status: 403, json: async () => ({ error: { code: 'link_declined', message: 'declined' } }) };
            state.linked = ['https://archive.example', ...JSON.parse(options.body).sites];
            return response({ linked: true, prompted: !state.wasLinked, sites: state.linked });
        }
        if (url.endsWith('/health')) {
            if (!state.linked) return { ok: false, status: 403, json: async () => ({ error: { code: 'origin_not_allowed', message: 'not linked' } }) };
            return response({ status: 'ok', twain_available: true, busy: false, link: { linked: true, sites: state.linked } });
        }
        if (options.method === 'POST') return response({ job_id: 'linked-job', status: 'queued' });
        return response({});
    }, true, { document, window: { location: { protocol: 'https:', origin: 'https://archive.example', pathname: '/archive/1/' } } });
    Object.assign(context.window.DLUX_STRINGS, { scan_linking_message: 'اختر السماح في نافذة ScanLink', scan_link_declined_message: 'لم يُسمح' });
    vm.runInContext(fs.readFileSync(buttonPath, 'utf8'), context);
    context.window.ScanLink.prototype.waitForResult = async () => 'pdf';
    return context.window.DluxScan;
}

{
    // First scan from an unlinked site links it with the administrator's list, then scans.
    const state = { calls: [], linkBodies: [], linked: null };
    const scan = linkingPage(['https://crm.example'], state);
    const progress = [];
    assert.equal(await scan.scan({ messages: scan.messagesFor(null), onProgress: (text) => progress.push(text) }), 'pdf');
    assert.deepEqual(state.linkBodies, [{ sites: ['https://crm.example'] }]);
    assert.ok(progress.includes('اختر السماح في نافذة ScanLink'));
    assert.deepEqual(state.calls.filter((call) => call.startsWith('POST')), ['POST /link', 'POST /scan']);
    passed++;

    // The same list does not link again; a changed list is sent without stopping the scan.
    state.calls.length = 0;
    state.wasLinked = true;
    assert.equal(await scan.scan({ messages: scan.messagesFor(null) }), 'pdf');
    assert.deepEqual(state.calls.filter((call) => call.startsWith('POST')), ['POST /scan']);
    passed++;
    const changedState = { calls: [], linkBodies: [], linked: ['https://archive.example', 'https://crm.example'], wasLinked: true };
    const resync = linkingPage(['https://sales.example'], changedState);
    assert.equal(await resync.scan({ messages: resync.messagesFor(null) }), 'pdf');
    assert.deepEqual(changedState.linkBodies, [{ sites: ['https://sales.example'] }]);
    passed++;

    // A declined link ends the scan with the translated reason and starts nothing.
    const declinedState = { calls: [], linkBodies: [], linked: null, declined: true };
    const declined = linkingPage([], declinedState);
    await assert.rejects(declined.scan({ messages: declined.messagesFor(null) }), (error) => error.code === 'link_declined' && error.message === 'لم يُسمح');
    assert.ok(!declinedState.calls.includes('POST /scan'));
    passed++;
}

// DjangoLux's own client hardening (break-it round 2: R2-053, R2-116, R2-117,
// the widened-list window). The helper's standalone client is not run here.
const never = (options) => new Promise((resolve, reject) => {
    if (options && options.signal) options.signal.addEventListener('abort', () => reject(new Error('aborted')));
});

{
    // R2-053: an answer that is not ScanLink's health shape is not ScanLink.
    const context = runtime(clientPath, async () => response({ hello: 'world', version: '9.9.9' }));
    const client = vm.runInContext('new ScanLink()', context);
    assert.equal(await client.checkHealth(true), null);
    assert.equal(client.connectionError.code, 'helper_unavailable');
    passed++;
}

{
    // R2-053: bytes that are not a PDF never become the field's file.
    const context = runtime(clientPath, async (url) => {
        if (url.endsWith('/result')) return { ok: true, blob: async () => new Blob(['<html>not a scan</html>'], { type: 'application/pdf' }) };
        if (url.includes('/scan/')) return response({ job_id: 'fake', status: 'completed', page_count: 1 });
        return response({ status: 'ok' });
    });
    const client = vm.runInContext('new ScanLink()', context);
    await assert.rejects(client.waitForResult('fake', { pollIntervalMs: 1 }), (error) => error.code === 'invalid_result');
    passed++;
}

{
    // R2-116: a frozen helper ends the wait with helper_stalled, status and result alike.
    let mode = 'status';
    const context = runtime(clientPath, async (url, options) => {
        if (mode === 'status' && url.includes('/scan/')) return never(options);
        if (url.endsWith('/result')) return never(options);
        if (url.includes('/scan/')) return response({ job_id: 'frozen', status: 'completed', page_count: 1 });
        return response({ status: 'ok' });
    });
    const client = vm.runInContext('new ScanLink({ statusTimeoutMs: 20, resultTimeoutMs: 20, stallWindowMs: 60 })', context);
    let started = Date.now();
    await assert.rejects(client.waitForResult('frozen', { pollIntervalMs: 5, timeoutMs: 5000 }), (error) => error.code === 'helper_stalled');
    assert.ok(Date.now() - started < 1000, 'the status stall ends within the stall window');
    mode = 'result';
    started = Date.now();
    await assert.rejects(client.getResult('frozen', 20), (error) => error.code === 'helper_stalled');
    assert.ok(Date.now() - started < 500);
    passed++;

    // A single slow status answer is retried, not fatal.
    let slow = 1;
    const retry = runtime(clientPath, async (url, options) => {
        if (url.includes('/scan/') && slow-- > 0) return never(options);
        if (url.endsWith('/result')) return { ok: true, blob: async () => new Blob(['%PDF-1.7']) };
        if (url.includes('/scan/')) return response({ job_id: 'slow', status: 'completed', page_count: 2 });
        return response({ status: 'ok' });
    });
    const retryClient = vm.runInContext('new ScanLink({ statusTimeoutMs: 20, stallWindowMs: 5000 })', retry);
    assert.equal(await (await retryClient.waitForResult('slow', { pollIntervalMs: 5 })).text(), '%PDF-1.7');
    passed++;

    // The whole wait is bounded by its deadline even when no read ever returns.
    const deadlineContext = runtime(clientPath, async (url, options) => never(options));
    const deadlineClient = vm.runInContext('new ScanLink({ statusTimeoutMs: 10000, stallWindowMs: 10000 })', deadlineContext);
    started = Date.now();
    await assert.rejects(deadlineClient.waitForResult('stuck', { pollIntervalMs: 5, timeoutMs: 60 }), (error) => error.code === 'scan_timeout');
    assert.ok(Date.now() - started < 1000, 'the deadline is not checked only between polls');
    passed++;
}

{
    // R2-117: codes the page knows are translated; anything else shows the page's
    // own failed message, never ScanLink's English text or exception details.
    const document = { querySelectorAll: () => [], addEventListener() {} };
    const context = runtime(clientPath, async () => response({ status: 'ok' }), true, { document });
    Object.assign(context.window.DLUX_STRINGS, {
        scan_lost_message: 'فُقد المسح', scan_failed_message: 'تعذر المسح', scan_stalled_message: 'المساعد متوقف',
        scan_link_rate_limited_message: 'انتظر', scan_invalid_result_message: 'ليس PDF',
    });
    vm.runInContext(fs.readFileSync(buttonPath, 'utf8'), context);
    const scan = context.window.DluxScan;
    const messages = scan.messagesFor(null);
    const expected = {
        job_not_found: 'فُقد المسح', result_unavailable: 'فُقد المسح', helper_stalled: 'المساعد متوقف',
        link_rate_limited: 'انتظر', invalid_result: 'ليس PDF', unexpected_error: 'تعذر المسح', scan_failed: 'تعذر المسح',
        pdf_generation_failed: 'تعذر المسح', callback_not_allowed: 'تعذر المسح', something_new: 'تعذر المسح',
    };
    for (const [code, text] of Object.entries(expected)) {
        assert.equal(scan.errorMessage(messages, { code, message: 'Traceback in C:\\Users\\op\\scanlink.py \u202Eevil' }), text, code);
    }
    passed++;
}

{
    // R2-052: with no data-scan-* attributes the page's strings table is used.
    const document = { querySelectorAll: () => [], addEventListener() {} };
    const context = runtime(clientPath, async () => response({ status: 'ok' }), true, { document });
    Object.assign(context.window.DLUX_STRINGS, { scan_preparing_label: 'جارٍ التحضير', scan_page_progress_template: 'تم مسح الصفحة {count}' });
    vm.runInContext(fs.readFileSync(buttonPath, 'utf8'), context);
    const messages = context.window.DluxScan.messagesFor({ dataset: {} });
    assert.equal(messages.preparing, 'جارٍ التحضير');
    assert.equal(messages.pageTemplate, 'تم مسح الصفحة {count}');
    assert.equal(context.window.DluxScan.messagesFor({ dataset: { scanPreparing: 'override' } }).preparing, 'override');
    passed++;
}

{
    // A linked site whose list gains a site waits on ScanLink's window: say so.
    const changedState = { calls: [], linkBodies: [], linked: ['https://archive.example'], wasLinked: true };
    const widened = linkingPage(['https://sales.example'], changedState);
    const progress = [];
    assert.equal(await widened.scan({ messages: widened.messagesFor(null), onProgress: (text) => progress.push(text) }), 'pdf');
    assert.ok(progress.includes('اختر السماح في نافذة ScanLink'), JSON.stringify(progress));
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
{
    const nodes = new Map();
    for (const name of ['connection', 'local-version', 'latest-version', 'status', 'actions', 'notice']) {
        nodes.set(`[data-scanlink-${name}]`, { textContent: '', hidden: true, children: [], replaceChildren() { this.children = []; }, appendChild(node) { this.children.push(node); } });
    }
    const card = {
        dataset: { origins: JSON.stringify(['https://localhost:5443']), manifestUrl: '/manifest' },
        querySelector: (selector) => nodes.get(selector), isConnected: true,
    };
    let linked = false;
    const clicks = [];
    const document = {
        readyState: 'complete', querySelectorAll: () => [card],
        createElement: () => ({ setAttribute() {}, addEventListener(type, handler) { clicks.push(handler); } }),
    };
    const DluxScan = { messagesFor: () => ({ linking: 'Choose Allow' }), link: async () => { linked = true; } };
    runtime(updatePath, async (url) => {
        if (url === '/manifest') return response({ latest_version: '0.8.0', downloads: { x64: '/installer' } });
        if (!linked) return { ok: false, status: 403, json: async () => ({ error: { code: 'origin_not_allowed' } }) };
        return response({ version: '0.8.0', https_setup: 'ready' });
    }, true, { document, window: { DluxScan } });
    await new Promise((resolve) => setTimeout(resolve, 20));
    assert.equal(nodes.get('[data-scanlink-connection]').textContent, 'Not allowed here');
    assert.match(nodes.get('[data-scanlink-status]').textContent, /has not allowed this site/);
    assert.equal(nodes.get('[data-scanlink-actions]').children.length, 1);
    await clicks[0]();
    assert.equal(nodes.get('[data-scanlink-connection]').textContent, 'Connected');
    passed++;
}
console.log(JSON.stringify({ passed }));

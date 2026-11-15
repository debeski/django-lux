// Runs the real section_manager.js against a minimal DOM and prints the markup
// its View and blocked-Delete modals insert, as JSON for
// `test_section_manager_js.py`. Every value the server sends is stored data.
import fs from 'node:fs';
import vm from 'node:vm';

const PAYLOAD = '<img src=x onerror="window.__fired=1">';

const listeners = {};
const domReady = [];
const inserted = [];
const modalEl = { remove() {}, addEventListener() {} };
let nextResponse = null;

const document = {
    cookie: '',
    body: {
        addEventListener(type, handler) { (listeners[type] ||= []).push(handler); },
        insertAdjacentHTML(_position, html) { inserted.push(html); },
    },
    addEventListener(type, handler) { if (type === 'DOMContentLoaded') domReady.push(handler); },
    getElementById(id) {
        if (id === 'sectionData') {
            return { textContent: JSON.stringify({ csrf: 't', deleteUrl: '/delete', detailsUrl: '/details' }) };
        }
        if (id === 'sectionManagerModal') return inserted.length ? modalEl : null;
        return null;
    },
};

const context = {
    document,
    console,
    setTimeout,
    bootstrap: { Modal: class { show() {} } },
    fetch: async () => ({ json: async () => nextResponse }),
    confirm: () => true,
    alert: () => {},
};
context.window = context;
vm.createContext(context);
vm.runInContext(fs.readFileSync(process.argv[2], 'utf8'), context);
domReady.forEach((handler) => handler());

async function fire(type, data, response) {
    nextResponse = response;
    inserted.length = 0;
    const event = { detail: { data }, target: { closest: () => null }, stopImmediatePropagation() {} };
    (listeners[type] || []).forEach((handler) => handler(event));
    await new Promise((resolve) => setTimeout(resolve, 20));
    return inserted.join('');
}

const record = { model: 'affiliate', id: 1, name: PAYLOAD };
const results = {
    payload: PAYLOAD,
    view: await fire('dlux:record:view', record, {
        success: true,
        title: PAYLOAD,
        fields: { [PAYLOAD]: PAYLOAD, Empty: '' },
        related: { [PAYLOAD]: [PAYLOAD] },
    }),
    blockedDelete: await fire('dlux:record:delete', record, {
        success: false,
        related: { [PAYLOAD]: [PAYLOAD] },
    }),
    fired: Boolean(context.__fired),
};
process.stdout.write(JSON.stringify(results));

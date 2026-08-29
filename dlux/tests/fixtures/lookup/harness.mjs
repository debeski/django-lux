// Enough DOM to run `dlux/static/dlux/lookup/js/lookup.js` under node.
//
// The near-match panel and the typeahead are both plain DOM behaviour with no
// server half to assert against, and the bug this exists to catch — a handler
// bound per panel instead of on the document, so markup injected by a modal
// re-render stayed inert — is invisible to any test that only reads the source.
// So the real file is executed here, against a shim built to the one contract
// it relies on: attribute lookup, parent walking, and bubbling to the document.
import { readFileSync } from 'fs';

const listeners = new WeakMap();

function key(attr) {
    return attr.replace(/^data-/, '').replace(/-(.)/g, (_, c) => c.toUpperCase());
}

export function el(tag, attrs = {}) {
    const node = {
        tagName: tag, dataset: {}, children: [], parentElement: null,
        value: '', checked: false, textContent: attrs.textContent || '',
        _attrs: { ...attrs }, style: {}, innerHTML: '',
        classList: {
            _set: new Set(),
            add(c) { this._set.add(c); }, remove(c) { this._set.delete(c); },
            contains(c) { return this._set.has(c); },
            toggle(c, on) { on ? this._set.add(c) : this._set.delete(c); },
        },
        appendChild(child) { node.children.push(child); child.parentElement = node; return child; },
        setAttribute(k, v) { node._attrs[k] = v; },
        getAttribute(k) { return node._attrs[k] ?? null; },
        addEventListener(type, fn) {
            const map = listeners.get(node) || {};
            (map[type] = map[type] || []).push(fn);
            listeners.set(node, map);
        },
        dispatchEvent(event) {
            if (!event.target) event.target = node;
            for (let n = node; n; n = n.parentElement) {
                const map = listeners.get(n) || {};
                (map[event.type] || []).slice().forEach((fn) => fn(event));
            }
            const map = listeners.get(globalThis.document) || {};
            (map[event.type] || []).slice().forEach((fn) => fn(event));
            return true;
        },
        querySelector(sel) { return node.querySelectorAll(sel)[0] || null; },
        querySelectorAll(sel) {
            const parts = sel.split(' ').map((p) => p.replace(/[[\]]/g, ''));
            const out = [];
            (function walk(current) {
                current.children.forEach((child) => {
                    if (parts.length === 1) {
                        if (key(parts[0]) in child.dataset) out.push(child);
                    } else if (key(parts[0]) in child.dataset) {
                        child.children.forEach((g) => { if (g.tagName === parts[1]) out.push(g); });
                    }
                    walk(child);
                });
            }(node));
            return out;
        },
    };
    for (const [k, v] of Object.entries(attrs)) {
        if (k.startsWith('data-')) node.dataset[key(k)] = v;
    }
    return node;
}

globalThis.Event = class { constructor(type) { this.type = type; this.target = null; } };
globalThis.window = { setTimeout: () => 0 };
globalThis.document = {
    readyState: 'complete',
    _roots: [],
    createElement: (tag) => el(tag),
    querySelectorAll: (sel) => (sel.includes('dlux-lookup') ? globalThis.document._roots : []),
    addEventListener(type, fn) {
        const map = listeners.get(globalThis.document) || {};
        (map[type] = map[type] || []).push(fn);
        listeners.set(globalThis.document, map);
    },
    dispatchEvent(event) {
        const map = listeners.get(globalThis.document) || {};
        (map[event.type] || []).slice().forEach((fn) => fn(event));
    },
};

/** Build a lookup field, optionally with the refused-submit panel showing. */
export function field({ names, typedValue, near, ratio = '', allowCreate = true }) {
    const root = el('div', { 'data-dlux-lookup': '', 'data-lookup-ratio': ratio });
    const input = el('input', { 'data-lookup-text': '' });
    const hidden = el('input', { 'data-lookup-value': '' });
    const typed = el('input', { 'data-lookup-typed': '' });
    const confirm = el('input', { 'data-lookup-confirm': '' });
    const list = el('datalist', { 'data-lookup-options': '' });
    names.forEach(([id, name]) => {
        const option = el('option', { 'data-id': String(id) });
        option.value = name;
        list.appendChild(option);
    });
    input.value = typedValue;
    [input, hidden, typed, confirm, list].forEach((n) => root.appendChild(n));

    let pick = null;
    let consent = null;
    if (near) {
        const panel = el('div', { 'data-lookup-near': '' });
        pick = el('button', {
            'data-lookup-pick': '', 'data-lookup-pick-id': String(near[0]), textContent: near[1],
        });
        panel.appendChild(pick);
        if (allowCreate) {
            consent = el('input', { 'data-lookup-consent': '' });
            panel.appendChild(consent);
        }
        root.appendChild(panel);
    }
    return { root, input, hidden, typed, confirm, pick, consent };
}

export function loadScript(path) {
    (0, eval)(readFileSync(path, 'utf8'));
}

export function report(state) {
    process.stdout.write(JSON.stringify(state));
}

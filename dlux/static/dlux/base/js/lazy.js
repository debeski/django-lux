/* On-demand assets and one shared watch for added markup.
 *
 * DluxAssets loads the bundles published in #dlux-asset-bundles
 * (dlux/lazy_assets.py) once each: when markup matching a bundle's selector is
 * on the page at DOMContentLoaded or arrives through the dynamic modal, when a
 * tour button is clicked, or when code calls DluxAssets.load(name). A file the
 * page already includes is not fetched again. Injected tags carry this script's
 * CSP nonce, so they load under a nonce-only policy too.
 *
 * DluxDom.onAdded(selector, callback) calls back for every element matching
 * `selector` that is added to the document later, from a single observer that
 * filters by selector instead of each script rescanning the whole document.
 *
 * DluxDom.runScripts(root, response) runs the <script> tags that fetched markup
 * put into `root`. A script that carries the nonce of the response it came in
 * runs with this page's nonce; any other keeps its own, so a nonce-only policy
 * blocks inline script that markup smuggled in.
 */
(function () {
    'use strict';

    if (window.DluxAssets) return;

    const nonce = (document.currentScript && document.currentScript.nonce) || '';
    const files = new Map();
    const bundlePromises = new Map();
    const ready = new Set();
    let bundles = {};
    try {
        const data = document.getElementById('dlux-asset-bundles');
        bundles = (data && JSON.parse(data.textContent)) || {};
    } catch (error) {
        bundles = {};
    }

    function pathOf(url) {
        try {
            return new URL(url, document.baseURI).pathname;
        } catch (error) {
            return url;
        }
    }

    function alreadyOnPage(url, selector, attribute) {
        const path = pathOf(url);
        return Array.from(document.querySelectorAll(selector))
            .some((element) => element.getAttribute(attribute) && pathOf(element[attribute]) === path);
    }

    function inject(url, kind, beforeTheme) {
        const key = pathOf(url);
        if (files.has(key)) return files.get(key);
        const present = kind === 'js'
            ? alreadyOnPage(url, 'script[src]', 'src')
            : alreadyOnPage(url, 'link[rel="stylesheet"][href]', 'href');
        const promise = present ? Promise.resolve() : new Promise((resolve, reject) => {
            let element;
            if (kind === 'js') {
                element = document.createElement('script');
                element.src = url;
                element.async = false;
            } else {
                element = document.createElement('link');
                element.rel = 'stylesheet';
                element.href = url;
            }
            if (nonce) element.nonce = nonce;
            element.addEventListener('load', () => resolve(), { once: true });
            element.addEventListener('error', () => {
                // Forget the failure so a later load() tries the file again.
                files.delete(key);
                element.remove();
                reject(new Error(`Failed to load ${url}`));
            }, { once: true });
            const anchor = beforeTheme ? document.querySelector('meta[name="dlux-lazy-styles"]') : null;
            if (anchor) {
                anchor.parentNode.insertBefore(element, anchor);
            } else if (kind === 'css' && document.body) {
                document.body.appendChild(element);
            } else {
                document.head.appendChild(element);
            }
        });
        files.set(key, promise);
        return promise;
    }

    function load(name) {
        if (bundlePromises.has(name)) return bundlePromises.get(name);
        const bundle = bundles[name];
        if (!bundle) return Promise.reject(new Error(`Unknown asset bundle: ${name}`));
        const promise = Promise.all((bundle.css || []).map((url) => inject(url, 'css', !!bundle.css_before_theme)))
            .then(() => Promise.all((bundle.js || []).map((url) => inject(url, 'js'))))
            .then(() => { ready.add(name); });
        promise.catch((error) => {
            bundlePromises.delete(name);
            console.error(error);
        });
        bundlePromises.set(name, promise);
        return promise;
    }

    function needs(root, selector) {
        if (!root || !selector) return false;
        if (root.matches && root.matches(selector)) return true;
        return !!(root.querySelector && root.querySelector(selector));
    }

    /** Load every bundle that markup inside `root` needs; resolves when they
     *  have all run (at once when none is needed). */
    function ensure(root) {
        const scope = root || document;
        const wanted = Object.keys(bundles).filter((name) => needs(scope, bundles[name].selector));
        return Promise.all(wanted.map(load)).then(() => undefined);
    }

    /** Names of the bundles `root` needs that have not finished loading. */
    function missing(root) {
        const scope = root || document;
        return Object.keys(bundles).filter((name) => !ready.has(name) && needs(scope, bundles[name].selector));
    }

    window.DluxAssets = { load, ensure, missing };

    const watchers = [];
    let combined = '';
    let observer = null;

    function deliver(node) {
        if (!combined) return;
        const hit = node.matches(combined) || node.querySelector(combined);
        if (!hit) return;
        watchers.forEach((watcher) => {
            if (node.matches(watcher.selector)) watcher.callback(node);
            node.querySelectorAll(watcher.selector).forEach(watcher.callback);
        });
    }

    function onAdded(selector, callback) {
        watchers.push({ selector, callback });
        combined = watchers.map((watcher) => watcher.selector).join(', ');
        if (!observer && typeof MutationObserver === 'function') {
            observer = new MutationObserver((records) => {
                records.forEach((record) => {
                    record.addedNodes.forEach((node) => {
                        if (node.nodeType === 1) deliver(node);
                    });
                });
            });
            observer.observe(document.documentElement, { childList: true, subtree: true });
        }
    }

    function responseNonce(response) {
        const policy = (response && response.headers && response.headers.get('Content-Security-Policy')) || '';
        const match = /'nonce-([^']+)'/.exec(policy);
        return match ? match[1] : '';
    }

    function executable(script) {
        const type = (script.getAttribute('type') || '').trim().toLowerCase();
        return !type || type === 'module' || /^(text|application)\/(x-)?(java|ecma)script$/.test(type);
    }

    function runScripts(root, response, skip) {
        if (!root) return;
        const delivered = responseNonce(response);
        root.querySelectorAll('script').forEach((old) => {
            if (!executable(old) || (skip && skip(old))) return;
            const script = document.createElement('script');
            Array.from(old.attributes).forEach((attr) => {
                if (attr.name !== 'nonce') script.setAttribute(attr.name, attr.value);
            });
            const own = old.nonce || old.getAttribute('nonce') || '';
            const trusted = delivered && own === delivered;
            if (trusted && nonce) script.nonce = nonce;
            else if (own) script.nonce = own;
            if (!old.src) script.textContent = old.textContent;
            old.parentNode.replaceChild(script, old);
        });
    }

    window.DluxDom = { onAdded, runScripts };

    function scanPage() {
        ensure(document).catch(() => {});
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', scanPage);
    } else {
        scanPage();
    }
    document.addEventListener('dlux:modal-content-loaded', (event) => {
        ensure(event.target).catch(() => {});
    });

    // Pages that open settings editors (Options) fetch them once the page is idle,
    // so the first editor opens as quickly as it did when they loaded up front.
    window.addEventListener('load', () => {
        const warm = Array.from(document.querySelectorAll('[data-dlux-assets-warm]'))
            .flatMap((element) => element.dataset.dluxAssetsWarm.split(/\s+/))
            .filter((name) => name && bundles[name]);
        if (!warm.length) return;
        const start = () => warm.forEach((name) => load(name).catch(() => {}));
        if (typeof window.requestIdleCallback === 'function') {
            window.requestIdleCallback(start, { timeout: 3000 });
        } else {
            setTimeout(start, 200);
        }
    });

    // The guided tour loads with its first click.
    document.addEventListener('click', (event) => {
        const button = event.target && event.target.closest
            ? event.target.closest('#start-tour, [data-dlux-start-tour]')
            : null;
        if (!button) return;
        event.preventDefault();
        load('tutorial').then(() => {
            if (window.DluxTutorial) window.DluxTutorial.start();
        }).catch(() => {});
    });
}());

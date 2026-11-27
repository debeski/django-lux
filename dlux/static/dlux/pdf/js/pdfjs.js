/* PDF.js on demand.
 *
 * DluxPdfJs.load() resolves with the PDF.js library, importing it (the ES
 * module named by the "pdf" entry of #dlux-asset-bundles, dlux/lazy_assets.py)
 * the first time a viewer or page editor needs it. The worker defaults to the
 * same entry's worker. The library's getDocument() fills in DjangoLux's
 * options: the image decoders under wasm/<version>/ next to the library,
 * useWasm: false (the CSP allows no WebAssembly) and isEvalSupported: false.
 * A bare URL, string or byte array is taken as { url } or { data }.
 *
 * window.pdfjsLib is that same library once it has loaded. Until then it is a
 * stand-in for project code that calls PDF.js directly: its getDocument(...)
 * loads the library first, and a workerSrc set on its GlobalWorkerOptions
 * carries over. The stand-in, and destroy() on a loaded document (gone from
 * PDF.js 6; destroy the loading task instead), are deprecated (see
 * docs/deprecation-countdown.md); call DluxPdfJs.load() instead.
 */
(function () {
    'use strict';

    if (window.DluxPdfJs) return;

    function bundle() {
        try {
            const data = document.getElementById('dlux-asset-bundles');
            const bundles = (data && JSON.parse(data.textContent)) || {};
            return bundles.pdf || {};
        } catch (error) {
            return {};
        }
    }

    function documentOptions(source, wasmUrl) {
        let options;
        if (typeof source === 'string' || source instanceof URL) {
            options = { url: source };
        } else if (source instanceof ArrayBuffer || ArrayBuffer.isView(source)) {
            options = { data: source };
        } else {
            options = Object.assign({}, source);
        }
        if (!options.wasmUrl) options.wasmUrl = wasmUrl;
        if (options.useWasm === undefined) options.useWasm = false;
        options.isEvalSupported = false;
        return options;
    }

    function withDefaults(lib, wasmUrl) {
        const library = Object.assign({}, lib);
        library.getDocument = function (source) {
            const task = lib.getDocument(documentOptions(source, wasmUrl));
            task.promise.then(function (pdf) {
                if (typeof pdf.destroy !== 'function') pdf.destroy = function () { return task.destroy(); };
            }, function () {});
            return task;
        };
        return library;
    }

    let library = null;
    let pending = null;

    function load() {
        if (library) return Promise.resolve(library);
        if (pending) return pending;
        const urls = bundle();
        if (!urls.module) return Promise.reject(new Error('PDF.js is not available on this page.'));
        const standIn = window.pdfjsLib && window.pdfjsLib.__dluxDeferred ? window.pdfjsLib : null;
        pending = import(urls.module).then(function (lib) {
            if (!lib || typeof lib.getDocument !== 'function') throw new Error('PDF.js did not load.');
            const moduleUrl = new URL(urls.module, document.baseURI);
            const wasmUrl = new URL(`wasm/${lib.version}/`, moduleUrl).href;
            const workerSrc = (standIn && standIn.GlobalWorkerOptions.workerSrc) || urls.worker || '';
            if (!lib.GlobalWorkerOptions.workerSrc && workerSrc) lib.GlobalWorkerOptions.workerSrc = workerSrc;
            library = withDefaults(lib, wasmUrl);
            window.pdfjsLib = library;
            return library;
        });
        pending.catch(function () { pending = null; });
        return pending;
    }

    if (!window.pdfjsLib) {
        window.pdfjsLib = {
            __dluxDeferred: true,
            GlobalWorkerOptions: { workerSrc: '' },
            getDocument: function (source) {
                let task = null;
                let destroyed = false;
                const promise = load().then(function (lib) {
                    task = lib.getDocument(source);
                    if (destroyed) task.destroy();
                    return task.promise;
                });
                return {
                    promise: promise,
                    destroy: function () {
                        destroyed = true;
                        return task ? task.destroy() : promise.then(function () {}, function () {});
                    },
                };
            },
        };
    }

    window.DluxPdfJs = { load: load };
}());

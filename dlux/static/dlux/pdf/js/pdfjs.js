/* PDF.js on demand.
 *
 * DluxPdfJs.load() resolves with the PDF.js library, fetching it (asset bundle
 * "pdf") the first time a viewer or page editor needs it. Until then
 * window.pdfjsLib is a stand-in for project code that calls PDF.js directly:
 * its getDocument(...).promise loads the library first, and a workerSrc set on
 * its GlobalWorkerOptions carries over. The stand-in is deprecated (see
 * docs/deprecation-countdown.md); call DluxPdfJs.load() instead.
 */
(function () {
    'use strict';

    if (window.DluxPdfJs) return;

    function loaded() {
        const lib = window.pdfjsLib;
        return lib && !lib.__dluxDeferred ? lib : null;
    }

    let pending = null;

    function load() {
        const lib = loaded();
        if (lib) return Promise.resolve(lib);
        if (pending) return pending;
        if (!window.DluxAssets) return Promise.reject(new Error('PDF.js is not available on this page.'));
        const standIn = window.pdfjsLib;
        pending = window.DluxAssets.load('pdf').then(function () {
            const real = loaded();
            if (!real) throw new Error('PDF.js did not load.');
            const workerSrc = standIn && standIn.GlobalWorkerOptions && standIn.GlobalWorkerOptions.workerSrc;
            if (workerSrc && !real.GlobalWorkerOptions.workerSrc) real.GlobalWorkerOptions.workerSrc = workerSrc;
            return real;
        });
        pending.catch(function () { pending = null; });
        return pending;
    }

    if (!window.pdfjsLib) {
        window.pdfjsLib = {
            __dluxDeferred: true,
            GlobalWorkerOptions: { workerSrc: '' },
            getDocument: function (source) {
                const promise = load().then(function (lib) { return lib.getDocument(source).promise; });
                return {
                    promise: promise,
                    destroy: function () {
                        return promise.then(function (pdf) { return pdf.destroy(); }, function () {});
                    },
                };
            },
        };
    }

    window.DluxPdfJs = { load: load };
}());

(function () {
    function initializeViewer(viewer) {
        if (viewer.dataset.pdfViewerReady === "1") return;
        viewer.dataset.pdfViewerReady = "1";
        const pdfUrl = viewer.dataset.pdfUrl;
        const workerUrl = viewer.dataset.workerUrl;
        const canvas = viewer.querySelector("[data-pdf-canvas]");
        const fallback = viewer.querySelector("[data-pdf-fallback]");
        const pageLabel = viewer.querySelector("[data-pdf-page]");
        const pagesLabel = viewer.querySelector("[data-pdf-pages]");
        const previousButton = viewer.querySelector("[data-pdf-prev]");
        const nextButton = viewer.querySelector("[data-pdf-next]");
        const zoomInButton = viewer.querySelector("[data-pdf-zoom-in]");
        const zoomOutButton = viewer.querySelector("[data-pdf-zoom-out]");
        const printButton = viewer.querySelector("[data-pdf-print]");
        const fullscreenButton = viewer.querySelector("[data-pdf-fullscreen]");
        let pdfDocument = null;
        let loadingTask = null;
        let disposed = false;
        const modalRoot = viewer.closest(".modal");
        viewer.disposePdf = () => {
            disposed = true;
            modalRoot?.removeEventListener("hidden.bs.modal", viewer.disposePdf);
            if (loadingTask) loadingTask.destroy().catch(() => {});
        };
        modalRoot?.addEventListener("hidden.bs.modal", viewer.disposePdf);
        let pageNumber = 1;
        let scale = 1.2;
        let rendering = false;

        function useFallback() {
            if (disposed) return;
            viewer.classList.add("is-fallback");
            if (fallback) {
                fallback.src = `${pdfUrl}#toolbar=0&navpanes=0`;
            }
        }

        function renderPage() {
            if (disposed || !pdfDocument || rendering) return;
            rendering = true;
            pdfDocument.getPage(pageNumber).then(function (page) {
                const viewport = page.getViewport({ scale: scale });
                const context = canvas.getContext("2d");
                canvas.height = viewport.height;
                canvas.width = viewport.width;
                return page.render({ canvasContext: context, viewport: viewport }).promise;
            }).then(function () {
                rendering = false;
                pageLabel.textContent = pageNumber;
                pagesLabel.textContent = pdfDocument.numPages;
                previousButton.disabled = pageNumber <= 1;
                nextButton.disabled = pageNumber >= pdfDocument.numPages;
            }).catch(function () {
                rendering = false;
                useFallback();
            });
        }

        if (!window.pdfjsLib || !pdfUrl) {
            useFallback();
            return;
        }

        window.pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
        loadingTask = window.pdfjsLib.getDocument({ url: pdfUrl, isEvalSupported: false });
        loadingTask.promise.then(function (loadedPdf) {
            pdfDocument = loadedPdf;
            pagesLabel.textContent = pdfDocument.numPages;
            renderPage();
        }).catch(useFallback);

        previousButton.addEventListener("click", function () {
            if (pageNumber > 1) {
                pageNumber -= 1;
                renderPage();
            }
        });

        nextButton.addEventListener("click", function () {
            if (pdfDocument && pageNumber < pdfDocument.numPages) {
                pageNumber += 1;
                renderPage();
            }
        });

        zoomInButton.addEventListener("click", function () {
            scale = Math.min(scale + 0.2, 2.8);
            renderPage();
        });

        zoomOutButton.addEventListener("click", function () {
            scale = Math.max(scale - 0.2, 0.6);
            renderPage();
        });

        printButton.addEventListener("click", function () {
            const frame = document.createElement("iframe");
            frame.style.position = "fixed";
            frame.style.right = "0";
            frame.style.bottom = "0";
            frame.style.width = "0";
            frame.style.height = "0";
            frame.style.border = "0";
            frame.src = pdfUrl;
            frame.onload = function () {
                frame.contentWindow.focus();
                frame.contentWindow.print();
            };
            document.body.appendChild(frame);
            setTimeout(function () {
                frame.remove();
            }, 60000);
        });

        fullscreenButton.addEventListener("click", function () {
            if (viewer.requestFullscreen) {
                viewer.requestFullscreen();
            }
        });
    }

    function initializeAll(root) {
        (root || document).querySelectorAll(".dlux-pdf-viewer").forEach(initializeViewer);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            initializeAll(document);
        });
    } else {
        initializeAll(document);
    }

    const observer = new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            mutation.removedNodes.forEach(function (node) {
                if (node.disposePdf) node.disposePdf();
                if (node.querySelectorAll) node.querySelectorAll(".dlux-pdf-viewer").forEach((viewer) => viewer.disposePdf?.());
            });
            mutation.addedNodes.forEach(function (node) {
                if (node.nodeType !== 1) return;
                if (node.classList && node.classList.contains("dlux-pdf-viewer")) {
                    initializeViewer(node);
                } else if (node.querySelectorAll) {
                    initializeAll(node);
                }
            });
        });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
})();

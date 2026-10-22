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
        let resizeObserver = null;
        const modalRoot = viewer.closest(".modal");
        viewer.disposePdf = () => {
            disposed = true;
            resizeObserver?.disconnect();
            document.removeEventListener("fullscreenchange", onFullscreenChange);
            modalRoot?.removeEventListener("hidden.bs.modal", viewer.disposePdf);
            if (loadingTask) loadingTask.destroy().catch(() => {});
        };
        modalRoot?.addEventListener("hidden.bs.modal", viewer.disposePdf);
        const stage = viewer.querySelector(".dlux-pdf-stage");
        const fullscreenIcon = fullscreenButton.querySelector("i");
        let pageNumber = 1;
        // 1 = the page fits the stage's width; zooming multiplies that.
        let zoom = 1;
        const ZOOM_MIN = 0.5;
        const ZOOM_MAX = 3;
        const ZOOM_STEP = 0.25;
        let rendering = false;
        let renderAgain = false;

        function useFallback() {
            if (disposed) return;
            viewer.classList.add("is-fallback");
            // The browser's own viewer has its own controls; these would do nothing.
            [previousButton, nextButton, zoomInButton, zoomOutButton].forEach((button) => { button.disabled = true; });
            if (fallback) {
                fallback.src = `${pdfUrl}#toolbar=0&navpanes=0`;
            }
        }

        function stageWidth() {
            const styles = window.getComputedStyle(stage);
            const padding = parseFloat(styles.paddingLeft) + parseFloat(styles.paddingRight);
            return Math.max(stage.clientWidth - padding, 120);
        }

        function renderPage() {
            if (disposed || !pdfDocument) return;
            // A click while a page is drawing is not dropped: draw again after.
            if (rendering) {
                renderAgain = true;
                return;
            }
            rendering = true;
            pdfDocument.getPage(pageNumber).then(function (page) {
                const fitWidth = stageWidth() / page.getViewport({ scale: 1 }).width;
                const cssScale = fitWidth * zoom;
                // Draw at the screen's pixel density so the page stays sharp,
                // and size the canvas in CSS pixels: that size is the zoom.
                const ratio = window.devicePixelRatio || 1;
                const viewport = page.getViewport({ scale: cssScale * ratio });
                const context = canvas.getContext("2d");
                canvas.height = Math.floor(viewport.height);
                canvas.width = Math.floor(viewport.width);
                canvas.style.width = `${Math.floor(viewport.width / ratio)}px`;
                canvas.style.height = `${Math.floor(viewport.height / ratio)}px`;
                return page.render({ canvasContext: context, viewport: viewport }).promise;
            }).then(function () {
                rendering = false;
                pageLabel.textContent = pageNumber;
                pagesLabel.textContent = pdfDocument.numPages;
                previousButton.disabled = pageNumber <= 1;
                nextButton.disabled = pageNumber >= pdfDocument.numPages;
                zoomOutButton.disabled = zoom <= ZOOM_MIN;
                zoomInButton.disabled = zoom >= ZOOM_MAX;
                viewer.dataset.pdfZoom = String(zoom);
                if (renderAgain) {
                    renderAgain = false;
                    renderPage();
                }
            }).catch(function () {
                rendering = false;
                useFallback();
            });
        }

        // Print and fullscreen work in the fallback too, so their handlers are
        // wired whether or not pdf.js can draw the file.
        if (!window.pdfjsLib || !pdfUrl) {
            useFallback();
        } else {
            window.pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;
            loadingTask = window.pdfjsLib.getDocument({ url: pdfUrl, isEvalSupported: false });
            loadingTask.promise.then(function (loadedPdf) {
                pdfDocument = loadedPdf;
                pagesLabel.textContent = pdfDocument.numPages;
                renderPage();
            }).catch(useFallback);
        }

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
            zoom = Math.min(zoom + ZOOM_STEP, ZOOM_MAX);
            renderPage();
        });

        zoomOutButton.addEventListener("click", function () {
            zoom = Math.max(zoom - ZOOM_STEP, ZOOM_MIN);
            renderPage();
        });

        // The fit width changes with the modal, the window and fullscreen.
        let lastWidth = 0;
        resizeObserver = new ResizeObserver(function () {
            const width = Math.round(stageWidth());
            if (width === lastWidth) return;
            lastWidth = width;
            renderPage();
        });
        resizeObserver.observe(stage);

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

        const enterLabel = fullscreenButton.title;
        const exitLabel = fullscreenButton.dataset.exitLabel || enterLabel;

        fullscreenButton.addEventListener("click", function () {
            if (document.fullscreenElement === viewer) {
                document.exitFullscreen().catch(() => {});
            } else if (viewer.requestFullscreen) {
                viewer.requestFullscreen().catch(() => {});
            }
        });

        // Esc leaves fullscreen too, so the button follows the document, not its own clicks.
        function onFullscreenChange() {
            const active = document.fullscreenElement === viewer;
            viewer.classList.toggle("is-fullscreen", active);
            fullscreenIcon.className = active ? "bi bi-fullscreen-exit" : "bi bi-arrows-fullscreen";
            fullscreenButton.title = active ? exitLabel : enterLabel;
            fullscreenButton.setAttribute("aria-label", fullscreenButton.title);
            fullscreenButton.setAttribute("aria-pressed", active ? "true" : "false");
        }
        document.addEventListener("fullscreenchange", onFullscreenChange);
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

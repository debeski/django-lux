(function () {
    const EDITOR_VERSION = "1.1.0";

    if (window.DluxPdfEditor && window.DluxPdfEditor.version === EDITOR_VERSION) {
        window.DluxPdfEditor.initAll(document);
        return;
    }

    function formatLabel(template, values) {
        return String(template || "").replace(/\{(\w+)\}/g, function (_, key) {
            return Object.prototype.hasOwnProperty.call(values, key) ? values[key] : "";
        });
    }

    function editorStatus(shell, message, level) {
        const status = shell.querySelector("[data-editor-status]");
        status.textContent = message;
        status.className = `alert alert-${level || "info"} mt-3`;
    }

    function withTimeout(promise, timeoutMs, timeoutMessage) {
        let timeoutId = null;
        const timeout = new Promise(function (_, reject) {
            timeoutId = setTimeout(function () {
                reject(new Error(timeoutMessage));
            }, timeoutMs);
        });
        return Promise.race([promise, timeout]).finally(function () {
            clearTimeout(timeoutId);
        });
    }

    function initializeEditor(shell) {
        if (shell.dataset.pdfEditorReady === "1") return;

        const currentUrl = shell.dataset.currentUrl;
        const saveUrl = shell.dataset.saveUrl;
        const workerUrl = shell.dataset.workerUrl;
        const grid = shell.querySelector("[data-page-grid]");
        const fileInput = shell.querySelector("#dlux-pdf-file-input");
        const addFilesButton = shell.querySelector("[data-add-files]");
        const scanButton = shell.querySelector("[data-scan-pages]");
        const saveButton = shell.querySelector("[data-save-pdf]");
        const rotateSelectedButton = shell.querySelector("[data-rotate-selected]");
        const fitSelectedButton = shell.querySelector("[data-fit-selected]");
        const selectionCount = shell.querySelector("[data-selection-count]");
        const acceptExtensions = (shell.dataset.acceptExtensions || ".pdf").split(/\s+/).filter(Boolean);
        const convertUrl = shell.dataset.convertUrl || "";
        const csrfToken = (shell.querySelector("[name=csrfmiddlewaretoken]") || {}).value || "";
        const labels = {
            pdfJsFailed: shell.dataset.labelPdfjsFailed || "PDF.js failed to load. Reload the page and try again.",
            removePage: shell.dataset.labelRemovePage || "Remove page",
            pagesReady: shell.dataset.labelPagesReady || "{count} page(s) ready. Drag pages to reorder them.",
            pageShort: shell.dataset.labelPageShort || "p.",
            notAccepted: shell.dataset.labelNotAccepted || "This file type cannot be added.",
            converting: shell.dataset.labelConverting || "Preparing {name}...",
            rotate: shell.dataset.labelRotate || "Rotate page",
            selectPage: shell.dataset.labelSelectPage || "Select page",
            fitBadge: shell.dataset.labelFitBadge || "A4",
            selected: shell.dataset.labelSelected || "{count} selected",
            discardEdits: shell.dataset.labelDiscardEdits || "Discard unsaved PDF edits?",
            scanning: shell.dataset.labelScanning || "Scanning",
            scannerError: shell.dataset.labelScannerError || "Scanner app returned an error.",
            scanLinkUnavailable: shell.dataset.labelScanlinkUnavailable || "ScanLink is not available.",
            emptySave: shell.dataset.labelEmptySave || "Select at least one page before saving.",
            saving: shell.dataset.labelSaving || "Saving PDF...",
            saveFailed: shell.dataset.labelSaveFailed || "Failed to save PDF.",
            currentFile: shell.dataset.labelCurrentFile || "Current file",
            currentLoadFailed: shell.dataset.labelCurrentLoadFailed || "Current PDF could not be loaded. You can still add a new PDF from file or scanner.",
            noCurrent: shell.dataset.labelNoCurrent || "No current PDF. Add pages from file or scanner.",
        };
        if (!window.pdfjsLib) {
            const retries = Number(shell.dataset.pdfEditorPdfjsRetries || "0");
            if (retries < 20) {
                shell.dataset.pdfEditorPdfjsRetries = String(retries + 1);
                setTimeout(function () {
                    if (shell.isConnected) initializeEditor(shell);
                }, 100);
                return;
            }
            editorStatus(shell, labels.pdfJsFailed, "danger");
            return;
        }
        const modalElement = shell.closest(".modal");
        // Closing with unsaved page edits asks through DjangoLux's unsaved-changes
        // prompt (Save / Discard / Go back), the same one forms use.
        function guardClose(event) {
            if (!shell.isConnected || shell.dataset.dirty !== "1" || shell.dataset.saved === "1") return;
            if (modalElement.dataset.dluxPdfDiscard === "1") {
                delete modalElement.dataset.dluxPdfDiscard;
                return;
            }
            const guard = window.dluxUnsavedGuard;
            if (guard && typeof guard.prompt === "function") {
                if (typeof guard.skipPrompt === "function" && guard.skipPrompt()) return;
                event.preventDefault();
                guard.prompt({
                    onSave: function () { saveButton.click(); },
                    onDiscard: function () {
                        modalElement.dataset.dluxPdfDiscard = "1";
                        window.bootstrap.Modal.getOrCreateInstance(modalElement).hide();
                    },
                });
                return;
            }
            if (!window.confirm(labels.discardEdits)) event.preventDefault();
        }
        shell.disposePdfEditor = () => {
            shell.dataset.closed = "1";
            loadingTasks.forEach((task) => task.destroy().catch(() => {}));
            loadingTasks.clear();
            modalElement?.removeEventListener("hide.bs.modal", guardClose);
            modalElement?.removeEventListener("hidden.bs.modal", shell.disposePdfEditor);
        };
        modalElement?.addEventListener("hide.bs.modal", guardClose);
        modalElement?.addEventListener("hidden.bs.modal", shell.disposePdfEditor);
        const pages = [];
        const sourceFiles = {};
        const loadingTasks = new Set();
        let pendingSources = 0;
        let saving = false;
        let uploadCounter = 0;
        let draggedId = null;

        shell.dataset.pdfEditorReady = "1";
        window.pdfjsLib.GlobalWorkerOptions.workerSrc = workerUrl;

        // Moves a page next to `targetId` (after it when `after`), or to the end
        // when there is no target: a drop past the last card.
        function reorderPages(fromId, targetId, after) {
            if (!fromId || fromId === targetId) return;
            const fromIndex = pages.findIndex((item) => item.id === fromId);
            if (fromIndex < 0) return;
            const moved = pages.splice(fromIndex, 1)[0];
            const targetIndex = targetId ? pages.findIndex((item) => item.id === targetId) : -1;
            if (targetId && targetIndex < 0) {
                pages.splice(fromIndex, 0, moved);
                return;
            }
            pages.splice(targetId ? targetIndex + (after ? 1 : 0) : pages.length, 0, moved);
            shell.dataset.dirty = "1";
            renderGrid();
        }

        // The half of the card the pointer is over decides before/after,
        // mirrored in right-to-left layouts.
        function dropsAfter(card, event) {
            const rect = card.getBoundingClientRect();
            const rightHalf = event.clientX > rect.left + rect.width / 2;
            const rtl = window.getComputedStyle(card).direction === "rtl";
            return rtl ? !rightHalf : rightHalf;
        }

        grid.addEventListener("dragover", function (event) {
            if (draggedId) event.preventDefault();
        });
        grid.addEventListener("drop", function (event) {
            if (!draggedId || event.target.closest(".dlux-pdf-page-card")) return;
            event.preventDefault();
            reorderPages(draggedId, null, true);
        });

        function selectedPages() {
            return pages.filter((item) => item.selected);
        }

        function updateSelectionTools() {
            const count = selectedPages().length;
            if (rotateSelectedButton) rotateSelectedButton.disabled = saving || !count;
            if (fitSelectedButton) fitSelectedButton.disabled = saving || !count;
            if (selectionCount) selectionCount.textContent = count ? formatLabel(labels.selected, { count: count }) : "";
        }

        function changePages(targets, change) {
            if (!targets.length) return;
            targets.forEach(change);
            shell.dataset.dirty = "1";
            renderGrid();
        }

        function renderGrid() {
            saveButton.disabled = saving || pendingSources > 0 || !pages.length || shell.dataset.dirty !== "1";
            updateSelectionTools();
            grid.innerHTML = "";
            pages.forEach((item, index) => {
                const li = document.createElement("li");
                li.className = "dlux-pdf-page-card";
                li.draggable = true;
                li.dataset.pageId = item.id;

                li.classList.toggle("is-selected", !!item.selected);
                const thumb = document.createElement("div");
                thumb.className = "dlux-pdf-thumb";
                item.canvas.style.transform = item.rotate ? `rotate(${item.rotate}deg)` : "";
                thumb.appendChild(item.canvas);
                if (item.fit === "a4") {
                    const badge = document.createElement("span");
                    badge.className = "badge text-bg-info dlux-pdf-fit-badge";
                    badge.textContent = labels.fitBadge;
                    thumb.appendChild(badge);
                }
                thumb.addEventListener("click", function () {
                    item.selected = !item.selected;
                    renderGrid();
                });

                const select = document.createElement("input");
                select.type = "checkbox";
                select.className = "form-check-input dlux-pdf-page-select";
                select.checked = !!item.selected;
                select.title = labels.selectPage;
                select.setAttribute("aria-label", labels.selectPage);
                select.addEventListener("change", function () {
                    item.selected = select.checked;
                    renderGrid();
                });

                const rotateButton = document.createElement("button");
                rotateButton.type = "button";
                rotateButton.className = "btn btn-outline-secondary btn-sm";
                rotateButton.title = labels.rotate;
                rotateButton.setAttribute("aria-label", labels.rotate);
                rotateButton.innerHTML = '<i class="bi bi-arrow-clockwise"></i>';
                rotateButton.addEventListener("click", function () {
                    changePages([item], (page) => { page.rotate = ((page.rotate || 0) + 90) % 360; });
                });

                const footer = document.createElement("div");
                footer.className = "dlux-pdf-page-card-footer";
                const label = document.createElement("div");
                label.className = "dlux-pdf-page-label";
                label.textContent = `${index + 1}. ${item.label}`;
                const removeButton = document.createElement("button");
                removeButton.type = "button";
                removeButton.className = "btn btn-outline-danger btn-sm";
                removeButton.title = labels.removePage;
                removeButton.innerHTML = '<i class="bi bi-x-lg"></i>';
                removeButton.addEventListener("click", function () {
                    const pageIndex = pages.findIndex((page) => page.id === item.id);
                    if (pageIndex >= 0) {
                        shell.dataset.dirty = "1";
                        pages.splice(pageIndex, 1);
                        renderGrid();
                    }
                });

                footer.appendChild(select);
                footer.appendChild(label);
                footer.appendChild(rotateButton);
                footer.appendChild(removeButton);
                li.appendChild(thumb);
                li.appendChild(footer);

                li.addEventListener("dragstart", function () {
                    draggedId = item.id;
                    li.classList.add("is-dragging");
                });
                li.addEventListener("dragend", function () {
                    draggedId = null;
                    li.classList.remove("is-dragging");
                });
                li.addEventListener("dragover", function (event) {
                    event.preventDefault();
                });
                li.addEventListener("drop", function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    reorderPages(draggedId, item.id, dropsAfter(li, event));
                });

                grid.appendChild(li);
            });
            editorStatus(shell, formatLabel(labels.pagesReady, { count: pages.length }), pages.length ? "secondary" : "warning");
        }

        async function renderThumbnail(pdfDocument, pageNumber) {
            const page = await pdfDocument.getPage(pageNumber);
            const viewport = page.getViewport({ scale: 0.24 });
            const canvas = document.createElement("canvas");
            canvas.width = viewport.width;
            canvas.height = viewport.height;
            await page.render({ canvasContext: canvas.getContext("2d"), viewport: viewport }).promise;
            return canvas;
        }

        async function addPdfSource(source, label, pdfDocument) {
            for (let pageNumber = 1; pageNumber <= pdfDocument.numPages; pageNumber += 1) {
                if (shell.dataset.closed === "1" || !shell.isConnected) break;
                const canvas = await renderThumbnail(pdfDocument, pageNumber);
                if (shell.dataset.closed === "1" || !shell.isConnected) break;
                pages.push({
                    id: `${source}-${pageNumber}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
                    source: source,
                    page: pageNumber,
                    label: `${label} ${labels.pageShort}${pageNumber}`,
                    canvas: canvas,
                    rotate: 0,
                    fit: null,
                    selected: false,
                });
                renderGrid();
            }
        }

        async function addFile(file, displayName) {
            if (saving || shell.dataset.closed === "1") return;
            const source = `upload_${uploadCounter}`;
            uploadCounter += 1;
            sourceFiles[source] = file;
            pendingSources += 1;
            saveButton.disabled = true;
            let task;
            try {
                const data = await file.arrayBuffer();
                if (shell.dataset.closed === "1") return;
                task = window.pdfjsLib.getDocument({ data: data, isEvalSupported: false });
                loadingTasks.add(task);
                const pdfDocument = await task.promise;
                await addPdfSource(source, displayName || file.name, pdfDocument);
                shell.dataset.dirty = "1";
            } finally {
                if (task) {
                    loadingTasks.delete(task);
                    await task.destroy().catch(() => {});
                }
                pendingSources -= 1;
                if (shell.dataset.closed !== "1") renderGrid();
            }
        }

        addFilesButton.addEventListener("click", function () {
            fileInput.click();
        });

        function extensionOf(name) {
            const match = /\.[^.]+$/.exec(String(name || "").toLowerCase());
            return match ? match[0] : "";
        }

        async function asPdfFile(file) {
            if (extensionOf(file.name) === ".pdf") return file;
            editorStatus(shell, formatLabel(labels.converting, { name: file.name }), "info");
            const formData = new FormData();
            formData.append("file", file, file.name);
            const response = await fetch(convertUrl, {
                method: "POST",
                body: formData,
                headers: { "X-CSRFToken": csrfToken, "X-Requested-With": "XMLHttpRequest" },
            });
            if (!response.ok) {
                let message = labels.notAccepted;
                try { message = (await response.json()).error || message; } catch (_) { /* keep default */ }
                throw new Error(message);
            }
            return new File([await response.blob()], `${file.name}.pdf`, { type: "application/pdf" });
        }

        fileInput.addEventListener("change", async function () {
            const chosen = Array.from(fileInput.files || []);
            fileInput.value = "";
            for (const file of chosen) {
                if (!acceptExtensions.includes(extensionOf(file.name)) || (extensionOf(file.name) !== ".pdf" && !convertUrl)) {
                    editorStatus(shell, labels.notAccepted, "danger");
                    continue;
                }
                try {
                    const pdfFile = extensionOf(file.name) === ".pdf" ? file : await asPdfFile(file);
                    await addFile(pdfFile, file.name);
                } catch (error) {
                    editorStatus(shell, error.message || labels.saveFailed, "danger");
                }
            }
        });

        if (rotateSelectedButton) rotateSelectedButton.addEventListener("click", function () {
            changePages(selectedPages(), (page) => { page.rotate = ((page.rotate || 0) + 90) % 360; });
        });

        if (fitSelectedButton) fitSelectedButton.addEventListener("click", function () {
            const targets = selectedPages();
            const fitAll = targets.some((page) => page.fit !== "a4");
            changePages(targets, (page) => { page.fit = fitAll ? "a4" : null; });
        });

        if (scanButton) scanButton.addEventListener("click", async function () {
            const originalHtml = scanButton.innerHTML;
            scanButton.disabled = true;
            scanButton.innerHTML = `<span class="spinner-border spinner-border-sm me-2"></span>${labels.scanning}`;
            try {
                if (!window.DluxScan) throw new Error(labels.scanLinkUnavailable);
                const blob = await window.DluxScan.scan({
                    messages: window.DluxScan.messagesFor(scanButton),
                    metadata: { path: window.location.pathname, surface: "pdf_editor" },
                    onProgress: function (text) {
                        if (shell.dataset.closed !== "1") editorStatus(shell, text, "info");
                    },
                });
                if (shell.dataset.closed === "1") return;
                await addFile(new File([blob], `scanned_${Date.now()}.pdf`, { type: "application/pdf" }));
            } catch (error) {
                if (shell.dataset.closed !== "1") editorStatus(shell, error.message || labels.scannerError, "danger");
            } finally {
                scanButton.disabled = false;
                scanButton.innerHTML = originalHtml;
            }
        });

        saveButton.addEventListener("click", async function () {
            if (saving || pendingSources || shell.dataset.closed === "1") return;
            if (!pages.length) {
                editorStatus(shell, labels.emptySave, "warning");
                return;
            }
            saveButton.disabled = true;
            saving = true;
            addFilesButton.disabled = true;
            if (scanButton) scanButton.disabled = true;
            updateSelectionTools();
            editorStatus(shell, labels.saving, "info");
            const formData = new FormData();
            formData.append("csrfmiddlewaretoken", csrfToken);
            formData.append("revision", shell.dataset.revision);
            formData.append("manifest", JSON.stringify(pages.map(function (item) {
                const entry = { source: item.source, page: item.page };
                if (item.rotate) entry.rotate = item.rotate;
                if (item.fit) entry.fit = item.fit;
                return entry;
            })));
            Object.keys(sourceFiles).forEach((source) => {
                formData.append(source, sourceFiles[source], sourceFiles[source].name);
            });
            try {
                const response = await fetch(saveUrl, {
                    method: "POST",
                    body: formData,
                    headers: {
                        "X-CSRFToken": csrfToken,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                });
                const text = await response.text();
                if (shell.dataset.closed === "1" || !shell.isConnected) return;
                let data;
                try { data = JSON.parse(text); } catch (_) { throw new Error(`${labels.saveFailed} (HTTP ${response.status})`); }
                if (!response.ok || !data.success) {
                    throw new Error(data.error || labels.saveFailed);
                }
                if (shell.dataset.modalMode === "1") {
                    const modalElement = shell.closest(".modal");
                    if (modalElement && window.bootstrap && window.bootstrap.Modal) {
                        const modal = window.bootstrap.Modal.getInstance(modalElement)
                            || window.bootstrap.Modal.getOrCreateInstance(modalElement);
                        shell.dataset.saved = "1";
                        modal.hide();
                    }
                    window.location.reload();
                    return;
                }
                window.location.href = data.redirect_url;
            } catch (error) {
                if (shell.dataset.closed === "1" || !shell.isConnected) return;
                saveButton.disabled = false;
                editorStatus(shell, error.message, "danger");
            } finally {
                saving = false;
                addFilesButton.disabled = false;
                if (scanButton) scanButton.disabled = false;
            }
        });

        if (currentUrl) {
            const loadingTask = window.pdfjsLib.getDocument({ url: currentUrl, isEvalSupported: false });
            loadingTasks.add(loadingTask);
            pendingSources += 1;
            saveButton.disabled = true;
            withTimeout(loadingTask.promise, 30000, labels.currentLoadFailed).then(async function (pdfDocument) {
                await addPdfSource("current", labels.currentFile, pdfDocument);
            }).catch(function () {
                if (shell.dataset.closed !== "1") editorStatus(shell, labels.currentLoadFailed, "warning");
            }).finally(function () {
                loadingTasks.delete(loadingTask);
                loadingTask.destroy().catch(() => {});
                pendingSources -= 1;
                if (shell.dataset.closed !== "1") saveButton.disabled = !pages.length || shell.dataset.dirty !== "1" || pendingSources > 0 || saving;
            });
        } else {
            saveButton.disabled = true;
            editorStatus(shell, labels.noCurrent, "warning");
        }
    }

    function initializeAll(root) {
        (root || document).querySelectorAll(".dlux-pdf-editor-shell").forEach(initializeEditor);
    }

    window.DluxPdfEditor = {
        version: EDITOR_VERSION,
        initAll: initializeAll,
    };

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
                if (node.disposePdfEditor) node.disposePdfEditor();
                if (node.querySelectorAll) node.querySelectorAll(".dlux-pdf-editor-shell").forEach((shell) => shell.disposePdfEditor?.());
            });
            mutation.addedNodes.forEach(function (node) {
                if (node.nodeType !== 1) return;
                if (node.classList && node.classList.contains("dlux-pdf-editor-shell")) {
                    initializeEditor(node);
                } else if (node.querySelectorAll) {
                    initializeAll(node);
                }
            });
        });
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
})();

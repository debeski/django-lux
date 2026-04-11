(function () {
    function archiveFileIcon(name) {
        const lower = (name || "").toLowerCase();
        if (lower.endsWith(".pdf")) return "bi bi-file-earmark-pdf-fill";
        if (/\.(png|jpe?g|gif|webp|svg)$/i.test(lower)) return "bi bi-file-earmark-image-fill";
        if (/\.(doc|docx|odt|rtf)$/i.test(lower)) return "bi bi-file-earmark-richtext-fill";
        if (/\.(xls|xlsx|csv)$/i.test(lower)) return "bi bi-file-earmark-spreadsheet-fill";
        return "bi bi-file-earmark-fill";
    }

    function archiveFileState(widget) {
        const input = widget.querySelector('[data-archive-file-input="true"]');
        const clearCheckbox = widget.querySelector(".archive-file-clear-checkbox");
        const initialName = widget.dataset.initialName || "";
        const initialUrl = widget.dataset.initialUrl || "";
        const initialIcon = widget.dataset.initialIcon || archiveFileIcon(initialName);

        if (input && input.files && input.files.length) {
            const file = input.files[0];
            return {
                mode: "selected",
                name: file.name,
                meta: widget.dataset.selectedMeta || "Ready to save with this form.",
                icon: archiveFileIcon(file.name),
                url: "",
                showClear: true,
            };
        }
        if (initialName && !(clearCheckbox && clearCheckbox.checked)) {
            return {
                mode: "initial",
                name: initialName,
                meta: widget.dataset.currentMeta || "Current file on this record.",
                icon: initialIcon,
                url: initialUrl,
                showClear: !!clearCheckbox,
            };
        }
        return {
            mode: "empty",
            name: widget.dataset.emptyTitle || "No file selected",
            meta: widget.dataset.emptyMeta || "Drop a file here or use the actions.",
            icon: "bi bi-file-earmark-arrow-up-fill",
            url: "",
            showClear: false,
        };
    }

    function syncArchiveFileWidget(widget) {
        const state = archiveFileState(widget);
        const icon = widget.querySelector("[data-archive-file-icon] i");
        const name = widget.querySelector("[data-archive-file-name]");
        const meta = widget.querySelector("[data-archive-file-meta]");
        const link = widget.querySelector("[data-archive-file-link]");
        const clearButton = widget.querySelector("[data-archive-file-clear]");

        if (icon) icon.className = state.icon;
        if (name) name.textContent = state.name;
        if (meta) meta.textContent = state.meta;
        if (link) {
            if (state.url) {
                link.href = state.url;
                link.hidden = false;
            } else {
                link.hidden = true;
                link.removeAttribute("href");
            }
        }
        if (clearButton) clearButton.hidden = !state.showClear;
        widget.classList.toggle("has-file", state.mode !== "empty");
    }

    function assignDroppedFiles(input, files) {
        if (!input || !files || !files.length) return;
        try {
            const dt = new DataTransfer();
            Array.from(files).forEach((file) => dt.items.add(file));
            input.files = dt.files;
            input.dispatchEvent(new Event("change", { bubbles: true }));
        } catch {
            // Ignore unsupported browsers.
        }
    }

    function initArchiveFileWidget(widget) {
        if (!widget || widget.dataset.archiveFileReady === "true") return;

        const input = widget.querySelector('[data-archive-file-input="true"]');
        const drop = widget.querySelector("[data-archive-file-drop]");
        const uploadButton = widget.querySelector("[data-archive-file-upload]");
        const clearButton = widget.querySelector("[data-archive-file-clear]");
        const clearCheckbox = widget.querySelector(".archive-file-clear-checkbox");

        if (!input || !drop) return;

        widget.dataset.archiveFileReady = "true";

        if (uploadButton) {
            uploadButton.addEventListener("click", function () {
                input.click();
            });
        }

        drop.addEventListener("click", function (event) {
            if (event.target.closest("a, button")) return;
            input.click();
        });

        drop.addEventListener("keydown", function (event) {
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                input.click();
            }
        });

        ["dragenter", "dragover"].forEach((eventName) => {
            drop.addEventListener(eventName, function (event) {
                event.preventDefault();
                widget.classList.add("is-dragover");
            });
        });

        ["dragleave", "dragend", "drop"].forEach((eventName) => {
            drop.addEventListener(eventName, function (event) {
                event.preventDefault();
                if (eventName === "drop") {
                    assignDroppedFiles(input, event.dataTransfer && event.dataTransfer.files);
                }
                widget.classList.remove("is-dragover");
            });
        });

        input.addEventListener("change", function () {
            if (clearCheckbox && input.files && input.files.length) {
                clearCheckbox.checked = false;
            }
            syncArchiveFileWidget(widget);
        });

        if (clearButton) {
            clearButton.addEventListener("click", function () {
                if (input.files && input.files.length) {
                    input.value = "";
                    if (clearCheckbox) clearCheckbox.checked = false;
                } else if (clearCheckbox) {
                    clearCheckbox.checked = true;
                }
                syncArchiveFileWidget(widget);
            });
        }

        syncArchiveFileWidget(widget);
    }

    window.initArchiveFileFields = function (scope) {
        (scope || document).querySelectorAll("[data-archive-file-widget]").forEach(initArchiveFileWidget);
    };

    document.addEventListener("DOMContentLoaded", function () {
        window.initArchiveFileFields(document);
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (!(node instanceof HTMLElement)) return;
                    if (node.matches("[data-archive-file-widget]")) initArchiveFileWidget(node);
                    if (node.querySelectorAll) {
                        node.querySelectorAll("[data-archive-file-widget]").forEach(initArchiveFileWidget);
                    }
                });
            });
        });
        observer.observe(document.body, { childList: true, subtree: true });
    });
})();

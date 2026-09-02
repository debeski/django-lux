(function () {
    function fileFieldIcon(name) {
        const lower = (name || "").toLowerCase();
        if (lower.endsWith(".pdf")) return "bi bi-file-earmark-pdf-fill";
        if (/\.(png|jpe?g|gif|webp|svg)$/i.test(lower)) return "bi bi-file-earmark-image-fill";
        if (/\.(doc|docx|odt|rtf)$/i.test(lower)) return "bi bi-file-earmark-richtext-fill";
        if (/\.(xls|xlsx|csv)$/i.test(lower)) return "bi bi-file-earmark-spreadsheet-fill";
        return "bi bi-file-earmark-fill";
    }

    function fileFieldState(widget) {
        const input = widget.querySelector('[data-dlux-file-input="true"]');
        const clearCheckbox = widget.querySelector(".dlux-file-clear-checkbox");
        const initialName = widget.dataset.initialName || "";
        const initialUrl = widget.dataset.initialUrl || "";
        const initialIcon = widget.dataset.initialIcon || fileFieldIcon(initialName);

        if (input && input.files && input.files.length) {
            const file = input.files[0];
            return {
                mode: "selected",
                name: file.name,
                meta: widget.dataset.selectedMeta || "Ready to save with this form.",
                icon: fileFieldIcon(file.name),
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

    function syncFileFieldWidget(widget) {
        const state = fileFieldState(widget);
        const icon = widget.querySelector("[data-dlux-file-icon] i");
        const name = widget.querySelector("[data-dlux-file-name]");
        const meta = widget.querySelector("[data-dlux-file-meta]");
        const link = widget.querySelector("[data-dlux-file-link]");
        const clearButton = widget.querySelector("[data-dlux-file-clear]");

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

    function syncFileFieldValidation(widget) {
        const input = widget.querySelector('[data-dlux-file-input="true"]');
        const feedback = widget.querySelector("[data-dlux-file-client-error]");
        const card = widget.querySelector("[data-dlux-file-drop]");
        if (!input) return true;

        const maxBytes = Number(input.dataset.maxFileBytes || 0);
        const file = input.files && input.files.length ? input.files[0] : null;
        let message = "";
        if (file && Number.isFinite(maxBytes) && maxBytes > 0 && file.size > maxBytes) {
            const limitMb = maxBytes / (1024 * 1024);
            const limitLabel = Number.isInteger(limitMb) ? String(limitMb) : limitMb.toFixed(1);
            const template = widget.dataset.tooLargeTemplate || "File exceeds the maximum allowed size ({limit} MB).";
            message = template.replace("{limit}", limitLabel);
        }

        input.setCustomValidity(message);
        widget.classList.toggle("is-invalid", Boolean(message));
        if (card) {
            if (message) card.setAttribute("aria-invalid", "true");
            else card.removeAttribute("aria-invalid");
        }
        if (feedback) {
            feedback.textContent = message;
            feedback.hidden = !message;
            feedback.classList.toggle("d-block", Boolean(message));
        }
        return !message;
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

    function initFileFieldWidget(widget) {
        if (!widget || widget.dataset.dluxFileReady === "true") return;

        const input = widget.querySelector('[data-dlux-file-input="true"]');
        const drop = widget.querySelector("[data-dlux-file-drop]");
        const uploadButton = widget.querySelector("[data-dlux-file-upload]");
        const libraryButton = widget.querySelector("[data-dlux-file-library]");
        const scanButton = widget.querySelector("[data-dlux-file-scan]");
        const clearButton = widget.querySelector("[data-dlux-file-clear]");
        const clearCheckbox = widget.querySelector(".dlux-file-clear-checkbox");

        if (!input || !drop) return;

        widget.dataset.dluxFileReady = "true";

        if (uploadButton) {
            uploadButton.addEventListener("click", function () {
                input.click();
            });
        }

        function runPrimaryAction() {
            if (widget.dataset.dluxFilePrimary === "library" && libraryButton) {
                libraryButton.click();
                return;
            }
            input.click();
        }

        if (scanButton) {
            ["pointerdown", "pointerup", "mousedown", "mouseup", "click", "dblclick"].forEach((eventName) => {
                scanButton.addEventListener(eventName, function (event) {
                    event.preventDefault();
                    event.stopPropagation();
                    if (typeof event.stopImmediatePropagation === "function") {
                        event.stopImmediatePropagation();
                    }
                });
            });
        }

        drop.addEventListener("click", function (event) {
            if (event.target.closest("[data-dlux-file-upload]")) return;
            if (event.target.closest("[data-dlux-file-library]")) return;
            if (event.target.closest("[data-asset-picker-library]")) return;
            if (event.target.closest("[data-dlux-file-scan]")) return;
            if (event.target.closest("[data-dlux-file-clear]")) return;
            if (event.target.closest("[data-dlux-file-link]")) return;
            if (event.target.closest("a, button")) return;
            runPrimaryAction();
        });

        drop.addEventListener("keydown", function (event) {
            if (event.target.closest("[data-asset-picker-library]")) return;
            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                runPrimaryAction();
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
            syncFileFieldWidget(widget);
            syncFileFieldValidation(widget);
        });

        if (clearButton) {
            clearButton.addEventListener("click", function () {
                if (input.files && input.files.length) {
                    input.value = "";
                    if (clearCheckbox) clearCheckbox.checked = false;
                } else if (clearCheckbox) {
                    clearCheckbox.checked = true;
                }
                syncFileFieldWidget(widget);
                syncFileFieldValidation(widget);
            });
        }

        syncFileFieldWidget(widget);
        syncFileFieldValidation(widget);
    }

    window.initFileFieldWidgets = function (scope) {
        (scope || document).querySelectorAll("[data-dlux-file-widget]").forEach(initFileFieldWidget);
    };

    document.addEventListener("DOMContentLoaded", function () {
        window.initFileFieldWidgets(document);
        const observer = new MutationObserver(function (mutations) {
            mutations.forEach(function (mutation) {
                mutation.addedNodes.forEach(function (node) {
                    if (!(node instanceof HTMLElement)) return;
                    if (node.matches("[data-dlux-file-widget]")) initFileFieldWidget(node);
                    if (node.querySelectorAll) {
                        node.querySelectorAll("[data-dlux-file-widget]").forEach(initFileFieldWidget);
                    }
                });
            });
        });
        observer.observe(document.body, { childList: true, subtree: true });
    });
})();

(function () {
    function csrfToken(picker) {
        const input = picker.closest('form')?.querySelector('input[name="csrfmiddlewaretoken"]');
        if (input) return input.value;
        const meta = document.querySelector('meta[name="csrf-token"]');
        if (meta) return meta.content || '';
        const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : '';
    }

    function setUploadError(picker, message) {
        const input = picker.querySelector('[data-asset-picker-upload]');
        const feedback = picker.querySelector('[data-dlux-file-client-error]');
        const card = picker.querySelector('[data-dlux-file-drop]');
        if (input) input.setCustomValidity(message || '');
        picker.classList.toggle('is-invalid', Boolean(message));
        if (card) {
            if (message) card.setAttribute('aria-invalid', 'true');
            else card.removeAttribute('aria-invalid');
        }
        if (feedback) {
            feedback.textContent = message || '';
            feedback.hidden = !message;
            feedback.classList.toggle('d-block', Boolean(message));
        }
    }

    function initializePicker(picker) {
        if (!picker || picker.dataset.assetPickerReady === 'true') return;
        picker.dataset.assetPickerReady = 'true';

        const valueInput = picker.querySelector('[data-asset-picker-value]');
        const clearInput = picker.querySelector('[data-asset-picker-clear-value]');
        const uploadInput = picker.querySelector('[data-asset-picker-upload]');
        const library = picker.querySelector('[data-asset-picker-library]');
        const toggle = picker.querySelector('[data-dlux-file-library]');
        const clearButton = picker.querySelector('[data-dlux-file-clear]');

        function syncCard(name, url, icon) {
            picker.dataset.initialName = name || '';
            picker.dataset.initialUrl = url || '';
            picker.dataset.initialIcon = icon || 'bi bi-file-earmark-image-fill';
            if (uploadInput) uploadInput.dispatchEvent(new Event('change', { bubbles: true }));
        }

        function closeLibrary() {
            if (!library || library.hidden) return;
            library.hidden = true;
            picker.classList.remove('is-library-open');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
        }

        function openLibrary() {
            if (!library) return;
            library.hidden = false;
            picker.classList.add('is-library-open');
            if (toggle) toggle.setAttribute('aria-expanded', 'true');
            const search = library.querySelector('[data-asset-picker-search]');
            if (search) search.focus();
        }

        if (toggle && library) {
            toggle.addEventListener('click', function (event) {
                event.preventDefault();
                event.stopPropagation();
                if (library.hidden) openLibrary();
                else closeLibrary();
            });
            document.addEventListener('click', function (event) {
                if (!picker.contains(event.target)) closeLibrary();
            });
            picker.addEventListener('keydown', function (event) {
                if (event.key === 'Escape') {
                    closeLibrary();
                    if (toggle) toggle.focus();
                }
            });
        }

        picker.addEventListener('click', function (event) {
            const option = event.target.closest('[data-asset-picker-option]');
            if (!option || !picker.contains(option)) return;
            picker.querySelectorAll('[data-asset-picker-option]').forEach(function (item) {
                item.classList.remove('is-selected');
            });
            option.classList.add('is-selected');
            valueInput.value = option.dataset.assetId || '';
            clearInput.checked = false;
            if (uploadInput) uploadInput.value = '';
            syncCard(
                option.dataset.assetName,
                option.dataset.assetUrl,
                picker.dataset.assetKind === 'font' ? 'bi bi-file-earmark-font-fill' : 'bi bi-file-earmark-image-fill'
            );
            closeLibrary();
            valueInput.dispatchEvent(new Event('change', { bubbles: true }));
        });

        const search = picker.querySelector('[data-asset-picker-search]');
        if (search) {
            search.addEventListener('input', function () {
                const query = search.value.trim().toLowerCase();
                picker.querySelectorAll('[data-asset-picker-option]').forEach(function (option) {
                    option.hidden = query && !(option.dataset.assetName || '').toLowerCase().includes(query);
                });
            });
        }

        if (uploadInput) {
            uploadInput.addEventListener('change', function () {
                const file = uploadInput.files && uploadInput.files[0];
                if (!file) return;
                picker.dataset.assetFallbackId = valueInput.value || '';
                picker.dataset.assetFallbackName = picker.dataset.initialName || '';
                picker.dataset.assetFallbackUrl = picker.dataset.initialUrl || '';
                picker.dataset.assetFallbackIcon = picker.dataset.initialIcon || '';
                valueInput.value = '';
                clearInput.checked = false;
                picker.querySelectorAll('[data-asset-picker-option]').forEach(function (item) {
                    item.classList.remove('is-selected');
                });

                const uploadUrl = picker.dataset.assetUploadUrl;
                if (!uploadUrl || picker.dataset.assetUploading === 'true') return;
                picker.dataset.assetUploading = 'true';
                setUploadError(picker, '');
                const body = new FormData();
                body.append('file', file);
                // Names the field this picker belongs to. The server resolves it
                // against its own registry for the namespace, the accepted kind
                // and the permission — it is not trusted for any of them.
                if (picker.dataset.assetField) body.append('field', picker.dataset.assetField);
                fetch(uploadUrl, {
                    method: 'POST',
                    body: body,
                    headers: {
                        'Accept': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': csrfToken(picker),
                    },
                })
                    .then(function (response) {
                        return response.json().then(function (data) {
                            if (!response.ok || !data.success) {
                                throw new Error(data.error || 'The file could not be uploaded.');
                            }
                            return data;
                        });
                    })
                    .then(function (data) {
                        document.dispatchEvent(new CustomEvent('dlux:managed-assets-uploaded', {
                            detail: { assets: data.assets || [], sourcePicker: picker },
                        }));
                    })
                    .catch(function (error) {
                        setUploadError(picker, error.message);
                    })
                    .finally(function () {
                        delete picker.dataset.assetUploading;
                    });
            });
        }

        if (clearButton) {
            clearButton.addEventListener('pointerdown', function () {
                picker.dataset.assetClearingUpload = uploadInput && uploadInput.files && uploadInput.files.length ? 'true' : 'false';
            });
            clearButton.addEventListener('click', function () {
                if (picker.dataset.assetClearingUpload === 'true') {
                    valueInput.value = picker.dataset.assetFallbackId || '';
                    clearInput.checked = false;
                    syncCard(
                        picker.dataset.assetFallbackName,
                        picker.dataset.assetFallbackUrl,
                        picker.dataset.assetFallbackIcon
                    );
                    return;
                }
                valueInput.value = '';
                clearInput.checked = true;
                picker.dataset.initialName = '';
                picker.dataset.initialUrl = '';
                picker.querySelectorAll('[data-asset-picker-option]').forEach(function (item) {
                    item.classList.remove('is-selected');
                });
                if (uploadInput) uploadInput.dispatchEvent(new Event('change', { bubbles: true }));
                valueInput.dispatchEvent(new Event('change', { bubbles: true }));
            });
        }
    }

    function initializeAll(root) {
        (root || document).querySelectorAll('[data-asset-picker]').forEach(initializePicker);
    }

    function addAssetOption(picker, asset) {
        if (!asset || String(asset.kind || '') !== String(picker.dataset.assetKind || '')) return null;
        const grid = picker.querySelector('[data-asset-picker-grid]');
        if (!grid) return null;
        let option = grid.querySelector(`[data-asset-picker-option][data-asset-id="${asset.id}"]`);
        if (!option) {
            option = document.createElement('button');
            option.type = 'button';
            option.className = 'dlux-file-library__option';
            option.dataset.assetPickerOption = '';
            option.dataset.assetId = String(asset.id || '');
            const image = document.createElement('img');
            image.alt = '';
            option.appendChild(image);
            option.appendChild(document.createElement('span'));
            grid.querySelector('[data-asset-picker-empty]')?.remove();
            grid.appendChild(option);
        }
        option.dataset.assetName = asset.title || '';
        option.dataset.assetUrl = asset.url || '';
        const image = option.querySelector('img');
        if (image) image.src = asset.url || '';
        const label = option.querySelector('span');
        if (label) label.textContent = asset.title || '';
        return option;
    }

    document.addEventListener('dlux:managed-assets-uploaded', function (event) {
        const detail = event.detail || {};
        const assets = Array.isArray(detail.assets) ? detail.assets : [];
        const sourcePicker = detail.sourcePicker;
        let sourceOption = null;
        document.querySelectorAll('[data-asset-picker]').forEach(function (picker) {
            assets.forEach(function (asset) {
                const option = addAssetOption(picker, asset);
                if (picker === sourcePicker && !sourceOption) sourceOption = option;
            });
        });
        if (sourceOption) {
            const uploadInput = sourcePicker.querySelector('[data-asset-picker-upload]');
            if (uploadInput) uploadInput.value = '';
            setUploadError(sourcePicker, '');
            sourceOption.click();
        }
    });

    document.addEventListener('DOMContentLoaded', function () { initializeAll(document); });
    new MutationObserver(function (mutations) {
        mutations.forEach(function (mutation) {
            mutation.addedNodes.forEach(function (node) {
                if (node.nodeType !== 1) return;
                if (node.matches?.('[data-asset-picker]')) initializePicker(node);
                initializeAll(node);
            });
        });
    }).observe(document.documentElement, { childList: true, subtree: true });
}());
